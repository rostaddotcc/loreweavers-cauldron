"""
Guardian — The Lore Weaver's Cauldron's mekaniska väktare
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
import random
import re
from typing import Callable, Coroutine
from urllib.parse import quote

from locations import clean_location_name, place_location, find_location, locations_match

# ── Tärningstärningar (Hit Dice, 5e) — storlek per klass ──
_HIT_DIE_BY_CLASS = {
    "barbarian": 12, "fighter": 10, "paladin": 10, "ranger": 10,
    "bard": 8, "cleric": 8, "druid": 8, "monk": 8, "rogue": 8, "warlock": 8, "artificer": 8,
    "sorcerer": 6, "wizard": 6,
}

def _hit_die_for_class(cls_name) -> str:
    """Tärningstärningens storlek per klass (5e). Default d8."""
    c = (cls_name or "").lower()
    for key, sides in _HIT_DIE_BY_CLASS.items():
        if key in c:
            return f"1d{sides}"
    return "1d8"

def _ability_mod(ch: dict, abbr: str) -> int:
    """Förmågemodifierare (t.ex. CON) ur character.abilities. Default 0."""
    try:
        mod = ch.get("abilities", {}).get(abbr, {}).get("mod", 0)
        return int(mod or 0)
    except (TypeError, ValueError):
        return 0

def _ensure_hit_dice(ch: dict) -> dict:
    """Se till att character.hit_dice finns: {dice, total, remaining}."""
    hd = ch.setdefault("hit_dice", {})
    if not isinstance(hd, dict) or not hd.get("dice"):
        hd["dice"] = _hit_die_for_class(ch.get("class", ""))
    hd["total"] = max(1, int(hd.get("total") or ch.get("level") or 1))
    hd.setdefault("remaining", hd["total"])
    return hd

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
7. Sätt FÖRDEL/NACKDEL i slutet av label när situationen ger det:
   - FÖRDEL (rulla 2d20, ta bästa): hjälp från allierad, dold/smygande, mål som är prone/blindad/fast, högre position.
   - NACKDEL (rulla 2d20, ta sämsta): mörker/dåliga förhållanden, Dodge, mål dolt, distraktion, stress.
   Format: label slutar med "FÖRDEL" eller "NACKDEL" (t.ex. "SMIDIGHET (DC 14) FÖRDEL").

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
You are a mechanical Lorekeeper for a D&D 5e RPG.
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
7. Add ADVANTAGE/DISADVANTAGE at the end of the label when the situation calls for it:
   - ADVANTAGE (roll 2d20, take best): help from an ally, hidden/sneaking, target is prone/blinded/restrained, higher ground.
   - DISADVANTAGE (roll 2d20, take worst): darkness/bad conditions, Dodge, target hidden, distraction, stress.
   Format: label ends with "ADVANTAGE" or "DISADVANTAGE" (e.g. "DEXTERITY (DC 14) ADVANTAGE").

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
Du är den mekaniska väktaren för The Lore Weaver's Cauldron, ett D&D 5e-rollspel.
Läs DM-svaret, spelarens handling och den senaste konversationshistoriken. \
Extrahera ALLA mekaniska effekter och uppdateringar.

## Vad du ska extrahera

### Strid & Hälsa
- damage: Skada som spelaren eller NPCs tar. Ange target ("player" eller NPC-namn), amount, type.
- healing: Läkning. Ange target och amount.
- death: NPCs som dör i denna scen. ENDAST om narrationen entydigt bekräftar döden \\
  ("dör", "faller död", "kollapsar och rör sig inte", "andas inte längre"). \\
  Om en NPC bara är sårad, bunden, medvetslös, flyr eller försvinner → INTE död. \\
  (P3-fix från playthrough: "Hooded Scavenger" markerades död trots att narrationen sa "levande, bunden".)

### Progression
- xp: Erfarenhetspoäng. ENDAST för: dråp/besegrade fiender, slutförda quests, \
  stora story-milstolpar, lösande av komplexa pussel/gåtor. \
  INTE för: vanliga NPC-samtal, titta på saker, gå från A till B, vila, köpa/sälja. \
  Om spelaren bara pratade med en NPC eller undersökte något → 0 XP.
- level_up: Sätt true om XP når nästa nivå.

### Föremål & Valuta
- items_add: Föremål spelaren FÅR (tar, hittar, köper, stjäl). Ange name, type, qty.
  Inkludera D&D-stats: damage (t.ex. "1d8 slashing"), damage_dice ("1d8"), damage_type ("slashing"),
  ac_bonus (heltal, t.ex. 14 för kedjerustning), range ("melee", "ranged 30/120"),
  properties (array: ["finesse","light"]), magic_bonus (0-3), charges, max_charges, description, effects.
  Klassificera varje föremål: category ("weapon"|"armor"|"potion"|"magic"|"tool"|"trinket") och
  usage ("wielded" — hålls i handen, "consumable" — förbrukas vid användning, "activated" — aktiveras med laddningar).
  Drycker och aktiverbara föremål: ange roll (t.ex. "2d4+2" för läkedryck) — tärningen som rullas vid användning.
  Ange ALLTID `weight` (flyttal, lbs) och `lore` (1-2 meningar stämningsfull världshistoria från kampanjens egen värld — var föremålet kommer ifrån, vem som ägde det. Aldrig referenser till andra verk. VARJE föremål MÅSTE ha lore.)
  `equipped`: sätt true ENDAST på föremål spelaren aktivt BÄR/ANVÄNDER nu (vapen i hand, rustning på sig). När spelaren byter vapen eller tar av sig rustning → items_remove för det gamla ELLER items_add med equipped:true för det nya + korrigering att det gamla inte längre bärs. Spelaren utrustar INTE själv — DM avgör vad som bärs.
  Vapen ska ha damage/damage_dice/damage_type. Rustning ska ha ac_bonus. Magiska föremål ska ha charges/effects/magic_bonus.
  Exempel vapen: {"name":"Långsvärd","type":"Vapen","category":"weapon","usage":"wielded","qty":1,"weight":3.0,"lore":"Smitt av Gråsmeden i Frostklippan, ärvd i tre generationer av vaktkaptener.","damage":"1d8 slashing","damage_dice":"1d8","damage_type":"slashing","range":"melee","properties":["versatile"],"magic_bonus":0,"equipped":true}
  Exempel rustning: {"name":"Kedjerustning","type":"Rustning","category":"armor","usage":"wielded","qty":1,"weight":25.0,"lore":"Smidd i Grådjupets tredje sal — den bär fortfarande märken efter den dvärg som bar den i hundra år.","ac_bonus":16,"description":"AC 16, stealth disadvantage","equipped":true}
  Exempel dryck: {"name":"Läkedryck","type":"Dryck","category":"potion","usage":"consumable","qty":1,"weight":0.5,"lore":"Bryggd av en kringvandrande helare — smaken av sött gräs och bittert järn.","roll":"2d4+2","effects":"Heals 2d4+2 HP","equipped":false}
  Exempel magiskt: {"name":"Eldtrollstav","type":"Magisk","qty":1,"weight":2.0,"lore":"Funnen i en utbränd trollkarlsgrav, fortfarande varm vid beröring.","damage":"2d6 fire","damage_dice":"2d6","damage_type":"fire","range":"ranged 120","magic_bonus":1,"charges":5,"max_charges":7,"effects":"Kan avfyra eldbollar","equipped":false}
- items_remove: Föremål spelaren FÖRLORAR (tappar, ger bort, säljer, förbrukar).
- currency: Valutaändringar. Ange denom (pp/gp/sp/cp) och amount (+ för in, - för ut).

### Uppdrag
- quests_new: Nya uppdrag. Ange name, description, reward (kort text), \
  xp_reward (heltal 100-500 beroende på svårighet), gold_reward (heltal, 0 om ingen guld-belöning). \
  Skapa ENDAST ett nytt uppdrag om spelaren faktiskt åtar sig ett mål — inte för varje litet samtal.
- quests_completed: Uppdrag som slutförs. Ange EXAKT namn ELLER quest-ID (se "Aktiva uppdrag" i tillståndet). \
  Matcha mot befintliga namn/ID, hitta inte på nya stavningar. \
  XP och guld betalas ut AUTOMATISKT från questens sparade reward — ange INTE samma XP igen i xp-fältet.
- quests_failed: Uppdrag som misslyckas. Samma regel: EXAKT befintligt namn eller ID.

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
- locations_new: Nya platser som nämns eller upptäcks. Ange objekt: {"name": "...", "description": "kort beskrivning av platsen", "lore": "1-2 meningar stämningsfull historia om platsen — varför den finns, vad som hänt där", "terrain": "skog|stad|berg|hav|grotta|öken|ruin|träsk|slätt|flod"}.
  VARJE ny plats MÅSTE ha description och lore — aldrig bara namnet. Exempel: {"name":"Gråporten","description":"En mossbelupen stenport i den norra muren","lore":"Byggd av de förlorade kungarna för att hålla något ute — ingen minns vad.","terrain":"ruin"}.
- current_location: Sällskapets NYA nuvarande plats — ENDAST om de faktiskt RÖR SIG dit i denna narration (reser, anländer, går in i en byggnad/plats). Ange platsens namn.
  Sätt INTE om: de bara nämner, planerar eller diskuterar en resa; de är kvar på samma plats. Om DM redan skrev [PLATS:namn] → ange samma namn (verifiering) eller null.
  Kontrollera "Location"/"Plats" i tillståndet — om den redan matchar den plats de är på, sätt null.
- world_lore: Varaktiga världsförändringar — konsekvenser av spelarens handlingar, rykten som sprids, platser som förändras, maktförskjutningar. Ange array av korta meningar (1 per förändring).
  ENDAST saker som faktiskt hänt och som världen minns — inte stämning, inte löften. Om inget → tom array.
- time_passed: Tid som förflyter. Ange hours och description.
- rest: Om spelaren vilar. Ange kind ("short" eller "long").
- new_day: Om en ny dag börjar. Ange description.

### Strid (chat-first combat)
- combat_start: Om en strid BÖRJAR i denna narration. Ange enemies: [{"name": "...", "hp": N, "ac": N, "max_hp": N}].
- combat_round: Om DM:n anger en ny runda ("Runda 2", "Next round"), sätt rundnumret (heltal).
- player_attacks: Spelarens attacker som DM narrerar. Ange: [{"target": "fiendnamn", "hit": true/false, "damage": N, "damage_type": "slashing", "crit": false}]. Extrahera ENDAST om DM explicit beskriver att spelaren träffar/missar och anger skada.
- enemy_attacks: Fiendernas attacker i denna tur. Ange ENDAST attackeraren (+ valfri damage_type om DM nämner vapen): [{"attacker": "goblin", "damage_type": "piercing"}]. KODEN rullar tärningen (d20 + attack_bonus mot spelarens AC) och skadan — fyll INTE i hit/damage/roll själv. Om DM:narrationen säger att fienden träffar/missar, ignorera det — koden bestämmer utfallet.
- combat_events: Övriga stridshändelser (flykt, status, förstärkningar, rundsammanfattning). Ange: ["Goblin flyr", "Runda 2 börjar"]. Skriv korta, informativa rader som fungerar som en stridslogg — spelaren ser dem i chatten.
- combat_end: Om striden SLUTAR (alla fiender döda/flydde eller spelaren flydde). Ange {"reason": "..."}.

### Tärningsresurser (roll_grants)
- roll_grants: Om DM ger spelaren en NY mekanisk fördel som innebär ett framtida tärningskast \
  (Bardic Inspiration, Second Wind, Bless, Guidance, Heroism, spell slot-dice, etc.). \
  Ange notation (t.ex. "1d6", "1d8+2"), label (kort namn), och reason (varför). \
  Exempel: DM säger "du får Bardic Inspiration" → {"notation": "1d6", "label": "Bardic Inspiration", "reason": "DM gav inspiration"}. \
  Om DM ger en buff utan tärning (t.ex. "du känner dig starkare") → tom array.
  VIKTIGT: Ge ALDRIG roll_grants för föremål som redan är konsumerade/använda (t.ex. en healing potion \
  som redan druckits) eller för resurser som nämns i minne/tillbakablick — bara för NYA fördelar som DM \
  ger i DENNA narration. Kontrollera state "Inventory" — om föremålet inte finns där, ge tom array.
- LÄKEDRYCK / HEALING POTION (KRITISKT): Om DM:n narrerar att spelaren DRICKER en läkedryck/healing potion \
  (t.ex. "du dricker läkedrycken", "hon tömmer flaskan") → ge roll_grant {"notation": "2d4+2", "label": "LÄKNING (läkedryck)", "reason": "läkedryck dracks"}. \
  Sätt INTE ett fast healing-belopp — spelaren ska rulla 2d4+2 själv. (5e: healing potion = 2d4+2 HP.)

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

### Korrigeringar (KRITISKT)
- corrections: Om DM:s narration implikerade att något hände som INTE borde ha hänt, korrigera det här. \
  Exempel: DM skrev "du tar boken" men spelaren bara läste i den → korrigera: {"field": "items_add", "action": "retract", "reason": "Spelaren läste bara i boken, plockade inte upp den"}. \
  NPC-BORTTAGNING: Om en NPC är en dubblett, sammanslagen, eller felaktigt tillagd → {"field": "npc_remove", "action": "remove", "names": ["Namn1", "Namn2"], "reason": "Dubblett / sammanslagen"}. \
  Andra exempel: DM gav XP för något spelaren inte gjorde, DM lade till föremål spelaren bara tittade på. \
  Om allt stämmer → tom array. Använd reason för att förklara för spelaren varför.

## Regler
1. Ta ENDAST med effekter som faktiskt sker — inte saker som nämns eller hotas.
2. "Du siktar mot flaskan" → INGET föremål. "Du tar flaskan" → items_add.
3. VIKTIGT — Föremål: lägg ENDAST till i items_add om spelaren FAKTISKT tar, får, köper eller stjäl föremålet i sin ägo. \
   "Du ser en bok" → INGET föremål. "Du läser boken" → INGET föremål (boken stannar). "Du plockar upp boken" → items_add. \
   "Du hittar en nyckel" → bara om spelaren tar den. "Du öppnar asken" → INGET föremäl om spelaren bara tittar i den.
4. Skippa föremål som redan finns i inventory (nedan) om de inte ges/tas igen.
5. XP: ENDAST vid: dråp (50-200 per fiende), slutfört quest (100-500), \
   story-milstolpe (50-300), komplex pussellösning (25-100). \
   ALDRIG XP för: NPC-samtal, undersökning, gång, vila, handel, vanliga interaktioner. \
   Noll XP är normalt — de flesta turer ger ingen XP.
6. Returnera ENDAST ett JSON-objekt. Inga förklaringar.
7. NPC-UPPDATERINGAR: Var AGGRESSIV med att uppdatera NPC-kort. Om en NPC nämns \
   i konversationen och du kan härleda ny information (namn, roll, relation, \
   personlighet, mål) → lägg till i npc_notes eller npc_relations. \
   Om en "okänd" NPC avslöjar sitt namn → npc_name_reveals.
8. KARAKTÄRSUPPDATERINGAR: Om spelaren upptäcker en ny förmåga, lär sig en \
   besvärjelse, eller om bakgrundshistorien utvecklas → character_updates.
9. ANTI-DUBBEL: Om DM:n redan använde en mekanisk tagg i narrationen \
   (t.ex. [SKADA:12], [GULD:15]) eller effekten tydligt redan är applicerad, \
   extrahera INTE samma effekt igen.

## SKADA & HP (KRITISKT — MISSA ALDRIG DETTA)
9. OM DM beskriver att spelaren TAR SKADA (huggs, bränns, faller, förgiftas, \
   träffas av magi, misslyckas med konsekvens) → SÄTT damage med target="player". \
   Läs DM-texten noggrant: "kylan biter", "blodet rinner", "du tappar andan", \
   "smärtan exploderar" = SKADA. Även implicit skada från misslyckade kast \
   (nat 1, låga slag) ska ge damage om DM beskriver konsekvenser.
10. OM DM beskriver att en NPC TAR SKADA eller DÖR → SÄTT damage/death med NPC-namn. \
    "Morwenna faller", "skuggvarelsen upplöses", "vakten sjunker ihop" = death.
11. OM DM beskriver LÄKNING (dryck, magi, vila, bandage) → SÄTT healing.
12. UPPSKATTA skada: låg (1-4), medel (5-10), hög (11-20), dödlig (21+). \
    Vid tvekan, välj medel. Hellre för mycket än för lite — HP ska sjunka.

## KONFLIKTDETEKTERING (KRITISKT)
13. OM spelaren påstår sig ha föremål de INTE har i inventory (nedan) → \
    SÄTT corrections med field="items_add", action="retract", \
    reason="Spelaren påstår sig ha X men har det inte i inventory". \
    Exempel: Spelaren säger "jag tar min lampa" men inventory är tomt → correction.
14. OM spelaren påstår sig kunna göra något som strider mot karaktärsbladet \
    (t.ex. "jag flyger" utan flygförmåga) → correction.
15. OM DM accepterar en spelarpåhittad detalj som bryter mot världen \
    (t.ex. "jag tar min mobiltelefon") → correction.

## Format
{
  "damage": [{"target": "player", "amount": 12, "type": "slashing"}],
  "healing": [],
  "death": [],
  "xp": 0,
  "items_add": [{"name": "...", "type": "Vapen", "category": "weapon", "usage": "wielded", "qty": 1, "weight": 3.0, "lore": "Stulen från en fallen riddare vid Gråportens mur.", "damage": "1d8 slashing", "damage_dice": "1d8", "damage_type": "slashing", "ac_bonus": null, "range": "melee", "properties": ["versatile"], "magic_bonus": 0, "charges": null, "max_charges": null, "description": "", "effects": null, "roll": null}],
  "items_remove": [],
  "currency": [{"denom": "gp", "amount": 15}],
  "quests_new": [{"name": "...", "description": "...", "reward": "...", "xp_reward": 100, "gold_reward": 0}],
  "quests_completed": [],
  "quests_failed": [],
  "npcs_new": [{"name": "...", "role": "...", "relation": "neutral"}],
  "npc_relations": [],
  "npc_notes": [{"name": "...", "note": "..."}],
  "npc_name_reveals": [{"old_name": "okänd", "new_name": "...", "reveal_text": "..."}],
  "character_updates": [{"field": "trait", "text": "..."}],
  "locations_new": [],
  "current_location": null,
  "world_lore": [],
  "time_passed": null,
  "rest": null,
  "new_day": null,
  "day_summary": null,
  "logbook": "",
  "combat_start": null,
  "combat_round": null,
  "initiative_entries": [],
  "combat_end": null,
  "player_attacks": [],
  "enemy_attacks": [],
  "combat_events": [],
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

    # Bärvikt (D&D 5e: max = STR × 15)
    total_w = sum(float(it.get("weight", 0) or 0) * int(it.get("qty", 1) or 1) for it in inv)
    coin_wt = sum(cur.get(d, 0) for d in ("pp", "gp", "sp", "cp")) / 50  # 50 mynt = 1 lb
    max_w = float(ch.get("max_weight_lbs", 0) or 0)
    grand_total = total_w + coin_wt
    if max_w > 0:
        pct = round(grand_total / max_w * 100)
        parts.append(f"Bärvikt: {grand_total:.1f} / {max_w:.0f} lb ({pct}%)")
    else:
        parts.append(f"Bärvikt: {grand_total:.1f} lb")

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

    # Quests (aktiva + avslutade, så Guardian kan matcha exakta namn/ID)
    active_statuses = ("aktiv", "active")
    active = [q for q in quests if q.get("status") in active_statuses]
    if active:
        q_lines = []
        for q in active[:6]:
            qid = q.get("id", "")[:8] if q.get("id") else ""
            line = f"{q['name']}"
            if qid:
                line += f" [ID:{qid}]"
            q_lines.append(line)
        q_str = "; ".join(q_lines)
        q_label = "Active quests" if language == "en" else "Aktiva uppdrag"
        parts.append(f"{q_label}: {q_str}")
    done_statuses = ("slutförd", "completed", "misslyckad", "failed")
    done = [q for q in quests if q.get("status") in done_statuses]
    if done:
        d_str = "; ".join(q["name"] for q in done[:4])
        d_label = "Concluded quests (do not re-add)" if language == "en" else "Avslutade uppdrag (lägg ej till igen)"
        parts.append(f"{d_label}: {d_str}")

    # World
    if world.get("current_location"):
        loc_label = "Location" if language == "en" else "Plats"
        parts.append(f"{loc_label}: {world['current_location']}")
    if world.get("day"):
        day_label = "Day" if language == "en" else "Dag"
        parts.append(f"{day_label}: {world['day']}")

    # Combat (stridspågår) — ALLA deltagare inkl. spelaren med HP/AC så
    # Guardian kan extrahera rätt skada OCH justera allas HP nästa tur.
    combat = world.get("combat")
    if combat and combat.get("active"):
        if language == "en":
            parts.append(f"⚔ COMBAT: Round {combat.get('round', 1)}")
        else:
            parts.append(f"⚔ STRID: Runda {combat.get('round', 1)}")
        # Spelaren FÖRST — Guardian måste se sin egen HP/AC/status
        ch = state.get("character", {})
        hp = ch.get("hp", {})
        p_status = ch.get("statuses", [])
        p_status_str = f" [{', '.join(s.get('name', str(s)) for s in p_status)}]" if p_status else ""
        if language == "en":
            parts.append(f"  - PLAYER {ch.get('name', '?')} (HP {hp.get('current', '?')}/{hp.get('max', '?')}, AC {ch.get('ac', '?')}){p_status_str}")
        else:
            parts.append(f"  - SPELAREN {ch.get('name', '?')} (HP {hp.get('current', '?')}/{hp.get('max', '?')}, AC {ch.get('ac', '?')}){p_status_str}")
        for e in combat.get("enemies", []):
            if e.get("alive", True):
                status = ", ".join(e.get("statuses", [])) if e.get("statuses") else ""
                parts.append(f"  - {e.get('name', '?')} (HP {e.get('hp', '?')}/{e.get('max_hp', '?')}, AC {e.get('ac', '?')}){(' [' + status + ']') if status else ''}")
        initiative = combat.get("initiative", [])
        if initiative:
            order = ", ".join(f"{i.get('name', '?')} ({i.get('value', '?')})" for i in initiative)
            parts.append(f"Initiative: {order}")
        # Spelarens action economy (förbrukade vs tillgängliga)
        pa = combat.get("player_actions")
        if pa:
            avail = [k for k, v in pa.items() if v is not False]
            spent = [k for k, v in pa.items() if v is False]
            if avail:
                parts.append(f"Player actions available: {', '.join(avail)}")
            if spent:
                parts.append(f"Player actions spent: {', '.join(spent)}")
        # Senaste stridslogg (max 8 poster) — så Guardian ser vad som hänt
        clog = combat.get("log", [])
        if clog:
            recent_log = clog[-8:]
            log_label = "Combat log" if language == "en" else "Stridslogg"
            parts.append(f"{log_label}:")
            for entry in recent_log:
                actor = entry.get("actor", "system")
                name = entry.get("name", "") or ""
                text = entry.get("text", "")
                prefix = f"{name} " if name else ""
                parts.append(f"  · [{actor}] {prefix}{text}")

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
        "locations_new": [], "current_location": None, "world_lore": [], "time_passed": None, "rest": None,
        "new_day": None, "day_summary": None, "logbook": "",
        "combat_start": None, "combat_round": None,
        "initiative_entries": [], "combat_end": None,
        "player_attacks": [], "enemy_attacks": [], "combat_events": [],
        "enemy_actions": [], "status_apply": [], "roll_grants": [], "corrections": [],
    }

    for attempt in range(2):
        try:
            raw = await model_call_fn(messages)
        except Exception as e:
            logger.warning("Guardian post-DM LLM failed (attempt %d): %s", attempt + 1, e)
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
        ) + (1 if result.get("xp") else 0) + (1 if result.get("rest") else 0) \
          + (1 if result.get("current_location") else 0)

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

# Hit Dice per klass (D&D 5e) — medelvärde per nivå = hd//2 + CON-mod
_HD_BY_CLASS = {
    "barbarian": 12, "fighter": 10, "paladin": 10, "ranger": 10,
    "bard": 8, "cleric": 8, "druid": 8, "monk": 8, "rogue": 8,
    "warlock": 8, "sorcerer": 6, "wizard": 6,
}


def _combat_tag(combat: dict) -> str:
    """Maskinläsbar [COMBAT:<urlencoded-json>]-tagg för frontendens Krigsråd."""
    try:
        # Trimma loggen till senaste 20 poster (hela strider → enorm JSON annars)
        tag_data = dict(combat)
        log = tag_data.get("log")
        if isinstance(log, list) and len(log) > 20:
            tag_data["log"] = log[-20:]
        return f"[COMBAT:{quote(json.dumps(tag_data, ensure_ascii=False), safe='')}]"
    except Exception:
        return ""


def _unequip_same_type(inv: list, item_type: str, keep_name: str) -> None:
    """När ett nytt föremål utrustas, ta bort equipped från andra av samma typ.

    D&D-regel: ett vapen i hand, en rustning på sig. Bara det nya namnet
    behåller equipped:true. (DM/Guardian styr equip — spelaren utrustar
    inte själv via UI längre.)
    """
    for it in inv:
        if it.get("type") == item_type and it.get("name", "").lower() != keep_name.lower():
            it["equipped"] = False


# ══════════════════════════════════════════════════════════════════
# ITEM_SCHEMA — enda källan för inventory-föremål (Aug 2026)
# Varje väg som skapar/ändrar items (char-gen, Guardian items_add,
# PATCH inventory) kör _normalize_item() så alla fält alltid har samma
# form. Nya fält läggs till HÄR en gång — inte per anropsställe.
# ══════════════════════════════════════════════════════════════════
ITEM_CATEGORIES = {
    # type-sträng → category (normaliseras av _normalize_item)
    "vapen": "weapon",
    "rustning": "armor",
    "dryck": "potion",
    "magisk": "magic",
    "verktyg": "tool",
    "annat": "trinket",
    "weapon": "weapon",
    "armor": "armor",
    "potion": "potion",
    "magic": "magic",
    "tool": "tool",
    "trinket": "trinket",
    "other": "trinket",
}

# Lore-fallback per kategori — används BARA om LLM:n glömde lore.
# Kort, stämningsfull, kampanjneutral: inga hårdkodade platser/namn.
ITEM_LORE_FALLBACK = {
    "weapon": "Smidd för en hand som aldrig vek sig — eggen bär minnen av strid och överlevnad.",
    "armor": "Bärs av den som vägrar falla — bucklor vittnar om slag som kunde ha slutat annorlunda.",
    "potion": "Bryggd i hemlighet, förvarad i mörker — en klunk förändrar allt.",
    "magic": "Laddad med kraft ingen längre förstår — den väntar på rätt händer.",
    "tool": "Använd av en som förstod att överlevnad är hantverk — slitet, men pålitligt.",
    "trinket": "En liten sak från en svunnen tid — värdelös för de flesta, ovärderlig för dig.",
}

# Standardroll per kategori för drycker/aktiverbara (om LLM inte angav roll)
ITEM_ROLL_FALLBACK = {
    "potion": "2d4+2",
    "magic": None,
}


def _category_from_type(item_type: str) -> str:
    """Härled category ur type-strängen (case-insensitive, fuzzy)."""
    if not item_type:
        return "trinket"
    t = str(item_type).strip().lower()
    if t in ITEM_CATEGORIES:
        return ITEM_CATEGORIES[t]
    # Fuzzy: "vapen", "Långsvärd"→weapon, "rustning"→armor, "dryck"→potion
    for key, cat in (("vapen", "weapon"), ("rustning", "armor"), ("dryck", "potion"),
                     ("magisk", "magic"), ("verktyg", "tool"), ("weapon", "weapon"),
                     ("armor", "armor"), ("potion", "potion"), ("tool", "tool")):
        if key in t:
            return cat
    return "trinket"


def _usage_from_item(item_type: str, category: str, equipped: bool, charges) -> str:
    """Härled usage: wielded (hålls i hand), consumable (förbrukas), activated."""
    if charges is not None:
        return "activated"
    if equipped:
        return "wielded"
    if category in ("potion",):
        return "consumable"
    if category in ("weapon", "armor"):
        return "wielded"
    return "activated" if category == "magic" else "trinket"


def _normalize_item(raw: dict, lang: str = "sv") -> dict:
    """Normalisera ett item till ITEM_SCHEMA — samma form oavsett källa.

    Alla skapelsevägar (char-gen, Guardian items_add, PATCH inventory)
    kör denna. Säkerställer: alla fält finns med rätt typ, lore har
    fallback om LLM:n glömde den, category/usage/roll härleds.
    """
    if not isinstance(raw, dict):
        raw = {}
    name = str(raw.get("name", "") or "").strip()
    item_type = str(raw.get("type", "") or "").strip() or ("Other" if lang == "en" else "Annat")
    category = str(raw.get("category", "") or "").strip().lower()
    if category not in ("weapon", "armor", "potion", "magic", "tool", "trinket"):
        category = _category_from_type(item_type)

    equipped = bool(raw.get("equipped", False))
    charges = raw.get("charges")
    usage = str(raw.get("usage", "") or "").strip().lower()
    if usage not in ("wielded", "consumable", "activated", "trinket"):
        usage = _usage_from_item(item_type, category, equipped, charges)

    qty = 1
    try:
        qty = max(1, int(raw.get("qty", 1) or 1))
    except (TypeError, ValueError):
        qty = 1
    weight = 1.0
    try:
        weight = float(raw.get("weight", 1) or 1)
    except (TypeError, ValueError):
        weight = 1.0

    rarity = str(raw.get("rarity", "normal") or "normal").strip() or "normal"
    if rarity not in ("normal", "magic", "rare", "legendary"):
        rarity = "normal"

    lore = raw.get("lore", None)
    if lore is None or not str(lore).strip():
        lore = ITEM_LORE_FALLBACK.get(category, ITEM_LORE_FALLBACK["trinket"])
    else:
        lore = str(lore).strip()

    props = raw.get("properties", []) if isinstance(raw.get("properties", []), list) else []
    props = [str(p) for p in props]

    item = {
        "name": name,
        "type": item_type,
        "category": category,
        "usage": usage,
        "qty": qty,
        "weight": weight,
        "lore": lore,
        "equipped": equipped,
        "rarity": rarity,
        "description": str(raw.get("description", "") or ""),
        "damage": raw.get("damage", None),
        "damage_dice": raw.get("damage_dice", None),
        "damage_type": raw.get("damage_type", None),
        "ac_bonus": raw.get("ac_bonus", None),
        "range": raw.get("range", None),
        "properties": props,
        "magic_bonus": _safe_int(raw.get("magic_bonus"), 0),
        "charges": charges,
        "max_charges": raw.get("max_charges", None),
        "effects": raw.get("effects", None),
        "roll": raw.get("roll", ITEM_ROLL_FALLBACK.get(category)),
    }
    # Behåll befintligt id om det finns (Guardian genererar annars)
    if raw.get("id"):
        item["id"] = str(raw["id"])
    return item


def _init_turn_order(combat: dict, state: dict) -> None:
    """Bygg turn_order från enemies + spelaren. Anropas vid combat_start."""
    ch = state.get("character", {})
    player_name = ch.get("name", "Spelaren")
    turn_order = [{"key": "player", "name": player_name, "initiative": 0, "acted": False}]
    for e in combat.get("enemies", []):
        if e.get("alive", True):
            turn_order.append({"key": f"enemy:{e.get('id', 0)}", "name": e.get("name", "?"), "initiative": 0, "acted": False})
    combat["turn_order"] = turn_order
    combat["current_index"] = 0
    combat.setdefault("player_actions", {"action": True, "bonus": True, "reaction": True})
    combat.setdefault("phase", "player")


def _advance_turn(combat: dict, state: dict) -> None:
    """Avancera turordningen: markera aktuell combatant som acted, stega
    current_index. När alla agerat → ny runda (round+1, reset acted)."""
    turn_order = combat.get("turn_order")
    if not turn_order:
        return
    idx = combat.get("current_index", 0)
    if idx < len(turn_order):
        turn_order[idx]["acted"] = True
    # Hitta nästa levande combatant
    next_idx = idx + 1
    # Kontrollera om alla agerat → ny runda
    if all(t.get("acted", False) for t in turn_order):
        combat["round"] = combat.get("round", 1) + 1
        for t in turn_order:
            t["acted"] = False
        combat["current_index"] = 0
        combat["phase"] = "player"
        combat.setdefault("player_actions", {"action": True, "bonus": True, "reaction": True})
        logger.info("⚔️ Ny runda %d — alla har agerat", combat["round"])
    else:
        # Stega till nästa levande combatant
        while next_idx < len(turn_order):
            entry = turn_order[next_idx]
            if entry["key"] == "player" or any(
                e.get("name", "").lower() == entry.get("name", "").lower() and e.get("alive", True)
                for e in combat.get("enemies", [])
            ):
                break
            next_idx += 1
        combat["current_index"] = min(next_idx, len(turn_order) - 1)
        current = turn_order[combat["current_index"]]
        combat["phase"] = "player" if current["key"] == "player" else "enemies"


def apply_mechanics(state: dict, mech: dict, skip_effects: list | None = None) -> list[dict]:
    """
    Applicera Guardian-extraherade mekaniska ändringar på state.

    skip_effects: effekter som REDAN applicerats denna tur via DM-taggar
    (t.ex. [SKADA:12], [GULD:15]) — de appliceras INTE en andra gång.
    Accepterar dicts ({"type": ..., "value": ...}) eller (type, value)-tupler.

    Returns:
        Lista av effect-dicts (för frontend-visuella effekter).
    """
    # P0-dedup: bygg nyckeluppsättning av redan applicerade effekter
    _skip_keys: set[tuple[str, str]] = set()
    for _se in (skip_effects or []):
        if isinstance(_se, dict):
            _skip_keys.add((str(_se.get("type", "")), str(_se.get("value", ""))))
        elif isinstance(_se, (tuple, list)) and len(_se) == 2:
            _skip_keys.add((str(_se[0]), str(_se[1])))

    effects: list[dict] = []
    ch = state.setdefault("character", {})

    # ── Skada ──
    for dmg in mech.get("damage", []):
        target = dmg.get("target", "player")
        amount = max(0, int(dmg.get("amount", 0)))
        if amount <= 0:
            continue
        # P0-dedup: [SKADA:]-taggen applicerade redan samma skada
        if ("skada", str(dmg.get("amount", 0))) in _skip_keys:
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
            logger.info("🛡️ Guardian: %d damage → HP %d/%d", dmg.get("amount", 0), hp["current"], hp["max"])
        else:
            # Fiende-skada — minska fiende-HP om fienden är i pågående strid
            combat = state.get("world", {}).get("combat")
            enemy = None
            if combat and combat.get("active"):
                enemy = next(
                    (e for e in combat.get("enemies", [])
                     if e.get("name", "").lower() == str(target).lower() and e.get("alive", True)),
                    None,
                )
            if enemy:
                enemy["hp"] = max(0, enemy.get("hp", 0) - amount)
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1),
                    "actor": "player",
                    "name": ch.get("name", "Spelaren"),
                    "text": f"träffar {enemy['name']} — {amount} skada ({dmg.get('type', 'okänd')})",
                })
                effects.append({"type": "combat_dmg", "value": enemy["name"], "amount": amount})
                logger.info("⚔️ Guardian: %s takes %d damage → %d/%d", enemy["name"], amount, enemy["hp"], enemy.get("max_hp", 0))
                if enemy["hp"] <= 0:
                    enemy["alive"] = False
                    effects.append({"type": "enemy_död", "value": enemy["name"]})
                    logger.info("💀 %s has fallen in battle", enemy["name"])
            else:
                _add_npc_note(state, target, f"Tog {amount} skada ({dmg.get('type', 'okänd')})")

    # ── Läkning ──
    for heal in mech.get("healing", []):
        target = heal.get("target", "player")
        amount = max(0, int(heal.get("amount", 0)))
        heal_type = str(heal.get("type", "")).lower()
        # LÄKEDRYCK-säkerhetsnät: om Guardian satte ett fast belopp för en
        # läkedryck/potion, konvertera till roll_grant (2d4+2) istället.
        # Spelaren ska rulla själv — 5e healing potion = 2d4+2 HP.
        _potion_kw = ("läkedryck", "potion", "healing potion", "health potion", "dryck")
        if target == "player" and any(kw in heal_type for kw in _potion_kw):
            lr = state.setdefault("meta", {}).setdefault("last_roll_requests", [])
            if not any(r.get("notation") == "2d4+2" and "LÄKNING" in r.get("label", "") for r in lr):
                lr.append({"notation": "2d4+2", "label": "LÄKNING (läkedryck)"})
            resources = state.setdefault("resources", [])
            if not any(r.get("notation") == "2d4+2" and "LÄKNING" in r.get("label", "") for r in resources):
                resources.append({"notation": "2d4+2", "label": "LÄKNING (läkedryck)", "reason": "läkedryck dracks", "turn": state.get("meta", {}).get("turn_count", 0)})
            effects.append({"type": "roll_grant", "value": "LÄKNING (läkedryck)", "notation": "2d4+2"})
            logger.info("🛡️ Guardian: läkedryck-healing → roll_grant 2d4+2 (istället för fast %d)", amount)
            continue
        if amount <= 0:
            continue
        # P0-dedup: [HELA:]-taggen applicerade redan samma läkning
        if ("hela", str(heal.get("amount", 0))) in _skip_keys:
            continue
        if target == "player":
            hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
            hp["current"] = min(hp.get("max", 1), hp.get("current", 0) + amount)
            effects.append({"type": "hela", "value": amount})
            logger.info("🛡️ Guardian: %d healing → HP %d/%d", amount, hp["current"], hp["max"])

    # ── Död ──
    # Robust mot både sträng- och dict-form (Guardian kan skicka death som
    # ["Namn"] ELLER [{"name": "Namn"}]) — dict-formen kraschade på
    # name.lower() (AttributeError 2026-08-02) → striden stängdes aldrig.
    for raw in mech.get("death", []):
        name = raw.get("name", "") if isinstance(raw, dict) else raw
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        for npc in state.get("npcs", []):
            if str(npc.get("name", "")).lower() == name.lower():
                npc["alive"] = False
                effects.append({"type": "npc_död", "value": name})
                logger.info("🛡️ Guardian: NPC '%s' dog", name)
                # Strid: markera fienden död i world.combat
                combat = state.get("world", {}).get("combat")
                if combat and combat.get("active"):
                    for e in combat.get("enemies", []):
                        if isinstance(e, dict) and str(e.get("name", "")).lower() == name.lower():
                            e["alive"] = False
                            effects.append({"type": "enemy_död", "value": name})
                            break
                break

    # Auto-avsluta strid när alla fiender är döda
    combat = state.get("world", {}).get("combat")
    if combat and combat.get("active") and combat.get("enemies"):
        if all(not e.get("alive", True) for e in combat.get("enemies", [])):
            combat["active"] = False
            combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "system", "name": "",
                "text": "Alla fiender besegrade — striden är över",
            })
            effects.append({"type": "combat_end", "value": "alla besegrade"})
            logger.info("🏁 Combat over — all enemies defeated")

    # ── XP ──
    xp_gain = max(0, int(mech.get("xp", 0)))
    if xp_gain > 0:
        # P0-dedup: [XP:]-taggen applicerade redan samma XP
        if ("xp", str(mech.get("xp", 0))) not in _skip_keys:
            xp = ch.setdefault("xp", {"current": 0, "next_level": 900})
            xp["current"] = xp.get("current", 0) + xp_gain
            effects.append({"type": "xp", "value": xp_gain})
            logger.info("🛡️ Guardian: +%d XP → %d", xp_gain, xp["current"])

            # Level-up check
            level = ch.get("level", 1)
            if level < len(_XP_THRESHOLDS) and xp["current"] >= _XP_THRESHOLDS[level]:
                ch["level"] = level + 1
                xp["next_level"] = _XP_THRESHOLDS[level + 1] if level + 1 < len(_XP_THRESHOLDS) else None
                # Max HP ökar — HD-baserat (medelvärde per nivå = hd//2 + CON-mod)
                hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
                con_mod = ch.get("abilities", {}).get("CON", {}).get("mod", 0)
                _cls = str(ch.get("class", "")).lower()
                _hd = _HD_BY_CLASS.get(_cls, 8)
                hp_gain = max(1, _hd // 2 + con_mod)
                hp["max"] = hp.get("max", 1) + hp_gain
                hp["current"] = hp["max"]  # Full HP vid level-up
                effects.append({"type": "level_up", "value": ch["level"]})
                logger.info("🛡️ Guardian: LEVEL UP → level %d! HP max %d (HD %d)", ch["level"], hp["max"], _hd)

    # ── Föremål ──
    inv = state.setdefault("inventory", [])
    # Bärvikt före denna tur (för viktkontroll — max_weight_lbs = STR × 15)
    current_weight = sum(float(it.get("weight", 0) or 0) * int(it.get("qty", 1) or 1) for it in inv)
    max_weight = float(ch.get("max_weight_lbs", 0) or 0)
    for item in mech.get("items_add", []):
        if not isinstance(item, dict):
            continue
        # ITEM_SCHEMA-normalisering (guardian.py _normalize_item) — samma
        # form som char-gen och PATCH inventory: category/usage/roll
        # härleds, lore får fallback om Guardian glömde den.
        norm = _normalize_item(item)
        name = norm["name"]
        if not name:
            continue
        # P0-dedup: [FÖREMÅL:]-taggen lade redan till samma föremål
        if ("föremål", name) in _skip_keys:
            continue
        qty = norm["qty"]
        item_weight = norm["weight"]
        added_weight = item_weight * qty
        # Viktkontroll: vägra om totalen skulle överskrida bärförmågan
        if max_weight > 0 and current_weight + added_weight > max_weight:
            logger.warning("🛡️ Guardian WEIGHT: '%s' (%.1f lb) refused — %.1f/%.1f lb", name, added_weight, current_weight, max_weight)
            effects.append({"type": "övervikt", "value": name, "weight": added_weight, "current": current_weight, "max": max_weight})
            continue
        existing = next((it for it in inv if it["name"].lower() == name.lower()), None)
        if existing:
            existing["qty"] = existing.get("qty", 1) + qty
            if item_weight > 0:
                existing["weight"] = item_weight  # uppdatera vikt om Guardian anger ny
            if norm.get("lore"):
                existing["lore"] = norm["lore"]
            # Uppdatera stat-fält om Guardian angav dem (första gången de dyker upp)
            for stat_key in ("category", "usage", "rarity", "damage", "damage_dice", "damage_type",
                             "ac_bonus", "range", "properties", "magic_bonus", "charges",
                             "max_charges", "effects", "roll", "description"):
                if norm.get(stat_key) is not None and norm.get(stat_key) != "":
                    existing[stat_key] = norm[stat_key]
            # Equip-status: Guardian/DM styr (spelaren utrustar inte själv)
            if norm.get("equipped"):
                _unequip_same_type(inv, norm["type"], name)
                existing["equipped"] = True
            logger.info("🛡️ Guardian dedup: '%s' → qty=%d", name, existing["qty"])
        else:
            new_item = dict(norm)
            new_item.setdefault("id", f"guardian-{len(inv)}")
            inv.append(new_item)
            if norm.get("equipped"):
                _unequip_same_type(inv, norm["type"], name)
            logger.info("🛡️ Guardian: added '%s'", name)
        current_weight += added_weight
        effects.append({"type": "föremål", "value": name, "qty": qty})

    for item in mech.get("items_remove", []):
        # Robust mot både dict- och sträng-form (samma klass av bugg som death)
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            qty = max(1, int(item.get("qty", 1)))
        elif isinstance(item, str):
            name = item.strip()
            qty = 1
        else:
            continue
        if not name:
            continue
        # P0-dedup: [FÖREMÅL_BORT:]-taggen tog redan bort samma föremål
        if ("föremål_bort", name) in _skip_keys:
            continue
        existing = next((it for it in inv if it["name"].lower() == name.lower()), None)
        if existing:
            existing["qty"] = existing.get("qty", 1) - qty
            if existing["qty"] <= 0:
                inv.remove(existing)
                # Om ett roll_grant-föremål förbrukas (t.ex. Healing Potion) —
                # ta bort matchande resurs ur state.resources så den inte
                # loopar som "Roll 🎲" / ny roll_grant i framtida turer.
                res = state.get("resources", [])
                kept = [r for r in res if (r.get("label") or "").strip().lower() != name.lower()]
                if len(kept) != len(res):
                    state["resources"] = kept
                    logger.info("🛡️ Removed resource '%s' (item consumed)", name)
                logger.info("🛡️ Guardian: removed '%s'", name)
            else:
                logger.info("🛡️ Guardian: reduced '%s' → qty=%d", name, existing["qty"])
            effects.append({"type": "föremål_bort", "value": name, "qty": qty})

    # ── Valuta ──
    cur = state.setdefault("currency", {"pp": 0, "gp": 0, "sp": 0, "cp": 0})
    for c in mech.get("currency", []):
        denom = c.get("denom", "gp").lower()
        amount = int(c.get("amount", 0))
        if denom in cur:
            # P0-dedup: [GULD:]-taggen applicerade redan samma ändring
            if ("guld", str(c.get("amount", 0))) in _skip_keys:
                continue
            cur[denom] = max(0, cur.get(denom, 0) + amount)
            effects.append({"type": "guld", "value": amount, "denom": denom})
            logger.info("🛡️ Guardian: %+d %s → %d", amount, denom, cur[denom])

    # ── Quests ──
    quests = state.setdefault("quests", [])

    def _norm_quest_name(s: str) -> str:
        """Normalisera quest-namn för robust matchning: lowercase, trim,
        kollapsade mellanslag, borttagna accenttecken."""
        import unicodedata
        s = unicodedata.normalize("NFKD", str(s))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(s.lower().split())

    def _find_quest(name_or_id: str, require_active: bool = True):
        """Hitta quest med ID-match (prioritet) eller normaliserad namnmatchning."""
        import uuid
        target = str(name_or_id).strip()
        active_set = ("aktiv", "active")
        
        # 1. Exakt ID-match (om det ser ut som UUID)
        if len(target) == 36 and target.count("-") == 4:
            for q in quests:
                if q.get("id") == target:
                    if not require_active or q.get("status") in active_set:
                        return q
        
        # 2. Normaliserad namnmatch
        norm_target = _norm_quest_name(target)
        for q in quests:
            if _norm_quest_name(q.get("name", "")) == norm_target:
                if not require_active or q.get("status") in active_set:
                    return q
        
        # 3. Substring-fallback (LLM kan parafrasera)
        for q in quests:
            qn = _norm_quest_name(q.get("name", ""))
            if norm_target and (norm_target in qn or qn in norm_target):
                if not require_active or q.get("status") in active_set:
                    return q
        return None

    for q in mech.get("quests_new", []):
        # Validera att entry är en dict (LLM kan skicka sträng → krasch annars)
        if not isinstance(q, dict):
            logger.warning("🛡️ Guardian: invalid quests_new entry (not dict): %r", q)
            continue
        name = str(q.get("name", "")).strip()
        if not name:
            continue
        if not _find_quest(name, require_active=False):
            import uuid
            quest_id = str(uuid.uuid4())
            quests.append({
                "id": quest_id,
                "name": name,
                "description": str(q.get("description", "")),
                "reward": str(q.get("reward", "")),
                "xp_reward": int(q.get("xp_reward", 100)),  # Default 100 XP
                "gold_reward": int(q.get("gold_reward", 0)),
                "status": "aktiv",
                "created_turn": state.get("meta", {}).get("turn_count", 0),
            })
            effects.append({"type": "quest", "value": name})
            logger.info("🛡️ Guardian: nytt uppdrag '%s' (ID: %s)", name, quest_id[:8])

    for name in mech.get("quests_completed", []):
        if not isinstance(name, str) or not name.strip():
            continue
        q = _find_quest(name, require_active=True)
        if q:
            q["status"] = "slutförd"
            q["completed_turn"] = state.get("meta", {}).get("turn_count", 0)
            effects.append({"type": "quest_slutförd", "value": q["name"]})
            logger.info("🛡️ Guardian: quest completed '%s'", q["name"])

            # ── Automatisk reward-utbetalning ──
            # XP-reward: hoppa över om LLM redan skickade samma XP via xp-fältet
            # (xp-sektionen ovan har redan applicerat det) eller om DM-tagg dedup
            xp_r = int(q.get("xp_reward", 0) or 0)
            llm_xp = int(mech.get("xp", 0) or 0)
            if xp_r > 0 and ("xp", str(xp_r)) not in _skip_keys and llm_xp != xp_r:
                xp = ch.setdefault("xp", {"current": 0, "next_level": 900})
                xp["current"] = xp.get("current", 0) + xp_r
                effects.append({"type": "xp", "value": xp_r, "source": "quest"})
                logger.info("🛡️ Guardian: +%d XP (quest-reward '%s') → %d", xp_r, q["name"], xp["current"])
                # Level-up check (samma logik som xp-sektionen)
                level = ch.get("level", 1)
                if level < len(_XP_THRESHOLDS) and xp["current"] >= _XP_THRESHOLDS[level]:
                    ch["level"] = level + 1
                    xp["next_level"] = _XP_THRESHOLDS[level + 1] if level + 1 < len(_XP_THRESHOLDS) else None
                    hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
                    con_mod = ch.get("abilities", {}).get("CON", {}).get("mod", 0)
                    _cls = str(ch.get("class", "")).lower()
                    _hd = _HD_BY_CLASS.get(_cls, 8)
                    hp_gain = max(1, _hd // 2 + con_mod)
                    hp["max"] = hp.get("max", 1) + hp_gain
                    hp["current"] = hp["max"]
                    effects.append({"type": "level_up", "value": ch["level"]})
                    logger.info("🛡️ Guardian: LEVEL UP (quest) → level %d!", ch["level"])

            # Guld-reward
            gold_r = int(q.get("gold_reward", 0) or 0)
            if gold_r > 0:
                cur = state.setdefault("currency", {"pp": 0, "gp": 0, "sp": 0, "cp": 0})
                cur["gp"] = cur.get("gp", 0) + gold_r
                effects.append({"type": "guld", "value": gold_r, "denom": "gp", "source": "quest"})
                logger.info("🛡️ Guardian: +%d gp (quest-reward '%s')", gold_r, q["name"])
        else:
            logger.warning("🛡️ Guardian: quests_completed matchade inget aktivt uppdrag: '%s'", name)

    for name in mech.get("quests_failed", []):
        if not isinstance(name, str) or not name.strip():
            continue
        q = _find_quest(name, require_active=True)
        if q:
            q["status"] = "misslyckad"
            effects.append({"type": "quest_misslyckad", "value": q["name"]})
            logger.info("🛡️ Guardian: uppdrag misslyckat '%s'", q["name"])
        else:
            logger.warning("🛡️ Guardian: quests_failed matchade inget aktivt uppdrag: '%s'", name)

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
                logger.info("🛡️ Guardian: NPC name revealed '%s' → '%s'", old_name, new_name)
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
            logger.info("🛡️ Guardian: new NPC via reveal '%s'", new_name)

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
        logger.info("🛡️ Guardian: character update '%s': %s", field, text[:60])

    # ── Platser ──
    world = state.setdefault("world", {})
    locations = state.setdefault("locations", [])  # fulla plats-objekt (platser.html + DM)
    for loc in mech.get("locations_new", []):
        if isinstance(loc, str):
            loc = {"name": loc}
        if not isinstance(loc, dict):
            continue
        name = clean_location_name(str(loc.get("name", "") or ""))
        if not name:
            continue
        # Dedup (2026-08-02): återanvänd kanoniskt namn om en nära-duplikat
        # redan finns i locations[] — annars växer kartan med dubbel-platser.
        loc_idx, loc_existing = find_location(locations, name)
        if loc_existing:
            name = loc_existing["name"]
        visited = world.setdefault("visited_locations", [])
        # Normalisera befintliga dict-poster → strängar (konsistens med
        # [PLATS:]-taggen; dicts i visited_locations bröt kartans visited-flagga)
        if any(isinstance(v, dict) for v in visited):
            visited[:] = [v.get("name", "") if isinstance(v, dict) else v for v in visited if (v.get("name", "") if isinstance(v, dict) else v)]
        exists = any(
            locations_match(str(v), name)
            for v in visited
        )
        if not exists:
            loc_obj = {
                "name": name,
                "description": str(loc.get("description", "") or ""),
                "lore": str(loc.get("lore", "") or ""),
                "terrain": str(loc.get("terrain", "okänd") or "okänd"),
                "turn": state.get("meta", {}).get("turn_count", 0),
                "visited": True,
            }
            visited.append(name)  # sträng — kartan kollar visited_names
            # Synka till state["locations"] (kartan + DM-prompten läser härifrån)
            if loc_idx is None:
                locations.append(loc_obj)
            effects.append({"type": "plats", "value": name})
            logger.info("🛡️ Guardian: ny plats '%s' (%s)", name, loc_obj["terrain"])

    # ── Nuvarande position (flytt) — DM kan uppdatera via [PLATS:]-taggen;
    # Guardian verifierar/detekterar och patchar annars (post-DM).
    # Dedup: om DM-taggen redan satte samma plats denna tur → ingen ändring.
    new_pos = mech.get("current_location")
    if new_pos and isinstance(new_pos, str):
        new_pos = clean_location_name(new_pos)
        old_pos = world.get("current_location", "")
        # Dedup: återanvänd kanoniskt namn om nära-duplikat finns i locations[]
        _pi, _pe = find_location(state.setdefault("locations", []), new_pos)
        if _pe:
            new_pos = _pe["name"]
        tag_applied = any(
            k[0] == "plats" and locations_match(str(k[1]), new_pos)
            for k in _skip_keys
        )
        if old_pos == new_pos or tag_applied:
            # DM gjorde rätt / DM-taggen applicerade redan — verifiera bara
            logger.info("🛡️ Guardian: position verifierad '%s' (oförändrad)", new_pos)
        else:
            if old_pos and old_pos != new_pos:
                world.setdefault("travel_log", []).append(
                    {"from": old_pos, "to": new_pos, "day": world.get("day", 1)}
                )
                logger.info("🛡️ Guardian: resa %s → %s (dag %d)", old_pos, new_pos, world.get("day", 1))
            world["current_location"] = new_pos
            visited = world.setdefault("visited_locations", [])
            # Normalisera befintliga dict-poster → strängar (konsistens med
            # [PLATS:]-taggen; dicts i visited_locations bröt kartans visited-flagga)
            if any(isinstance(v, dict) for v in visited):
                visited[:] = [v.get("name", "") if isinstance(v, dict) else v
                              for v in visited
                              if (v.get("name", "") if isinstance(v, dict) else v)]
            if new_pos not in visited:
                visited.append(new_pos)
            # Synka state["locations"] så kartan har koordinater + rätt current
            locations = state.setdefault("locations", [])
            if _pi is None:
                placed = place_location(new_pos, state.get("meta", {}).get("campaign_id", ""))
                locations.append({
                    "name": new_pos, "description": "", "terrain": placed["terrain"],
                    "x": placed["x"], "y": placed["y"], "visited": True,
                })
            effects.append({"type": "flytt", "value": new_pos})
            logger.info("🛡️ Guardian: position → '%s'", new_pos)

    # ── Världslore — varaktiga förändringar (stat.lore läses av DM-prompten) ──
    for lore_text in mech.get("world_lore", []):
        if not isinstance(lore_text, str) or not lore_text.strip():
            continue
        lore = state.setdefault("lore", [])
        t = lore_text.strip()
        if t not in lore:
            lore.append(t)
            effects.append({"type": "konsekvens", "value": t})
            logger.info("🛡️ Guardian: lore → %s", t[:80])

    # ── Tid ──
    tp = mech.get("time_passed")
    if tp and isinstance(tp, dict):
        hours = int(tp.get("hours", 0))
        desc = tp.get("description", "")
        if hours > 0:
            world["time"] = desc or world.get("time", "")
            effects.append({"type": "tid", "value": desc or f"{hours}h"})
            logger.info("🛡️ Guardian: %dh passes — %s", hours, desc)

    # ── Vila (5e: Hit Dice) ──
    rest = mech.get("rest")
    if rest and isinstance(rest, dict):
        kind = rest.get("kind", "short")
        hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
        hd = _ensure_hit_dice(ch)
        if kind == "long":
            hp["current"] = hp.get("max", 1)
            hp["temp"] = 0
            ss = ch.setdefault("spell_slots", {"current": 0, "max": 0})
            ss["current"] = ss.get("max", 0)
            hd["remaining"] = hd.get("total", 1)
            effects.append({"type": "hela", "value": hp.get("current", 0)})
            logger.info("🛡️ Guardian: LONG REST → full HP + spell slots + hit dice restored")
        else:
            # Kort vila (5e): spendera 1 Hit Die → 1dX + CON-mod
            if hd.get("remaining", 0) > 0:
                die = hd.get("dice", "1d8")
                sides = int(re.sub(r"[^0-9]", "", die) or 8)
                con_mod = _ability_mod(ch, "CON")
                rolled = random.randint(1, sides)
                heal = max(1, rolled + con_mod)
                hp["current"] = min(hp.get("max", 1), hp.get("current", 0) + heal)
                hd["remaining"] = int(hd.get("remaining", 1)) - 1
                effects.append({
                    "type": "vila", "value": hp.get("current", 0),
                    "detail": f"+{heal} HP ({die}{con_mod:+d}) · {hd['remaining']}/{hd.get('total', 1)} kvar",
                })
                logger.info("🛡️ Guardian: SHORT REST → +%d HP (%s%+d), %d/%d dice left",
                            heal, die, con_mod, hd["remaining"], hd.get("total", 1))
            else:
                effects.append({
                    "type": "vila", "value": hp.get("current", 0),
                    "detail": "inga tärningstärningar kvar — ingen läkning",
                })
                logger.info("🛡️ Guardian: SHORT REST without hit dice → no healing")

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

    # ── Strid (combat-tracker) — Guardian-extraherade fält ──
    world = state.setdefault("world", {})
    combat = world.get("combat")

    cs = mech.get("combat_start")
    if cs and isinstance(cs, dict):
        enemies_in = cs.get("enemies") or []
        enemies = []
        names = []
        for i, e in enumerate(enemies_in):
            name = (e.get("name") or "").strip()
            if not name:
                continue
            hp = _safe_int(e.get("hp"), 1)
            ac = _safe_int(e.get("ac"), 10)
            max_hp = _safe_int(e.get("max_hp"), hp)
            enemies.append({"id": i, "name": name, "hp": hp, "max_hp": max_hp, "ac": ac, "alive": True, "statuses": []})
            names.append(name)
        if enemies:
            if combat and combat.get("active"):
                # MERGE: strid redan aktiv — lägg till nya fiender, behåll befintliga
                existing_names = {e.get("name", "").lower() for e in combat.get("enemies", [])}
                next_id = max((e.get("id", 0) for e in combat.get("enemies", [])), default=-1) + 1
                added = []
                for e in enemies:
                    if e["name"].lower() not in existing_names:
                        e["id"] = next_id
                        next_id += 1
                        combat.setdefault("enemies", []).append(e)
                        added.append(e["name"])
                if added:
                    effects.append({"type": "combat_start", "value": ", ".join(added)})
                    logger.info("⚔️ Guardian combat_start (merge): +%s", ", ".join(added))
                # Sätt bara turn_order om den saknas
                if not combat.get("turn_order"):
                    _init_turn_order(combat, state)
            else:
                # NY strid — skapa från grunden
                world["combat"] = {
                    "active": True, "round": 1, "initiative": [],
                    "enemies": enemies, "log": [],
                    "started_turn": state.get("meta", {}).get("turn_count", 0),
                    "ended_turn": None,
                }
                combat = world["combat"]
                _init_turn_order(combat, state)
                effects.append({"type": "combat_start", "value": ", ".join(names)})
                logger.info("⚔️ Guardian combat_start: %s", ", ".join(names))

    cr = mech.get("combat_round")
    if cr and combat and combat.get("active"):
        new_round = _safe_int(cr, 0)
        if new_round > combat.get("round", 1):
            combat["round"] = new_round
            combat.setdefault("log", []).append({
                "round": new_round, "actor": "system", "name": "", "text": f"Runda {new_round} börjar",
            })
            effects.append({"type": "combat_round", "value": new_round})
            logger.info("⚔️ Guardian: ny runda %d", new_round)

    if combat and combat.get("active"):
        for ent in mech.get("initiative_entries", []) or []:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            value = _safe_int(ent.get("value"), 0)
            initiative = combat.setdefault("initiative", [])
            # Ersätt befintlig fiende-entry med samma namn, behåll ordning
            initiative[:] = [e for e in initiative if not (e.get("key") != "player" and e.get("name", "").lower() == name.lower())]
            eid = next((i for i, e in enumerate(combat.get("enemies", [])) if e.get("name", "").lower() == name.lower()), 0)
            initiative.append({"key": f"enemy:{eid}", "name": name, "value": value})
            effects.append({"type": "initiativ", "value": f"{name}: {value}"})
            logger.info("🎲 Guardian initiativ: %s → %d", name, value)

    ce = mech.get("combat_end")
    if ce and combat and combat.get("active"):
        reason = (ce.get("reason") or "striden avslutades") if isinstance(ce, dict) else str(ce)
        combat["active"] = False
        combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "system", "name": "", "text": f"Striden avslutades — {reason}",
        })
        effects.append({"type": "combat_end", "value": reason})
        logger.info("🏁 Guardian combat_end: %s", reason)

    # ── Chat-first combat: player_attacks, enemy_attacks, combat_events ──
    combat = state.get("world", {}).get("combat")
    if combat and combat.get("active"):
        combat_log = combat.setdefault("log", [])
        combat_log_len_before = len(combat_log)  # för deterministisk turn-avancering
        current_round = combat.get("round", 1)

        # Spelarens attacker → minska fiende-HP
        for atk in mech.get("player_attacks", []):
            target_name = str(atk.get("target", "")).strip()
            if not target_name:
                continue
            enemy = next((e for e in combat.get("enemies", []) if e.get("name", "").lower() == target_name.lower() and e.get("alive", True)), None)
            if not enemy:
                continue
            if atk.get("hit"):
                dmg = max(0, int(atk.get("damage", 0)))
                if dmg > 0:
                    enemy["hp"] = max(0, enemy.get("hp", 0) - dmg)
                    crit_str = " 💥 KRITISK!" if atk.get("crit") else ""
                    combat_log.append({"round": current_round, "actor": "player", "name": ch.get("name", "Spelaren"), "text": f"träffar {enemy['name']} — {dmg} skada ({atk.get('damage_type', 'okänd')}){crit_str}"})
                    effects.append({"type": "combat_dmg", "value": enemy["name"], "amount": dmg})
                    logger.info("⚔️ Player attack: %s → %s, %d skada → HP %d/%d", ch.get("name"), enemy["name"], dmg, enemy["hp"], enemy.get("max_hp", 0))
                    if enemy["hp"] <= 0:
                        enemy["alive"] = False
                        combat_log.append({"round": current_round, "actor": "system", "name": "", "text": f"{enemy['name']} faller!"})
                        effects.append({"type": "enemy_död", "value": enemy["name"]})
                        logger.info("💀 %s har fallit", enemy["name"])
            else:
                combat_log.append({"round": current_round, "actor": "player", "name": ch.get("name", "Spelaren"), "text": f"missar {enemy['name']}"})

        # Fiendernas attacker → KODEN rullar tärningarna (transparens — inte DM-fusk)
        # Guardian extraherar bara attackeraren; d20 + attack_bonus mot spelarens
        # AC och skade-tärningarna rullas här, precis som spelarens egna kast.
        hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
        player_ac = int(ch.get("ac", 10))
        for atk in mech.get("enemy_attacks", []):
            attacker_name = str(atk.get("attacker", "")).strip()
            if not attacker_name:
                continue
            enemy = next(
                (e for e in combat.get("enemies", [])
                 if e.get("name", "").lower() == attacker_name.lower() and e.get("alive", True)),
                None,
            )
            # Fiendens stats från combat (fallback: attackeraren finns inte i listan → använd DM:s angivna hit/damage om de finns)
            if enemy is not None:
                from combat import roll_d20, roll_dice as _roll_dice

                d20 = roll_d20()
                attack_bonus = int(enemy.get("attack_bonus", 3))
                total = d20 + attack_bonus
                crit = d20 == 20
                fumble = d20 == 1
                if fumble:
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"missar dig (nat 1!)"})
                    effects.append({"type": "enemy_miss", "value": attacker_name, "roll": total, "d20": d20, "bonus": attack_bonus})
                    continue
                if total < player_ac and not crit:
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"missar dig (🎲 d20={d20}+{attack_bonus}={total} mot AC {player_ac})"})
                    effects.append({"type": "enemy_miss", "value": attacker_name, "roll": total, "d20": d20, "bonus": attack_bonus})
                    continue
                # Träff → rulla skadan (fiendens damage_dice, fallback 1d6+1)
                dmg_notation = enemy.get("damage_dice", "1d6+1")
                dmg, rolls = _roll_dice(dmg_notation)
                if crit:
                    dmg2, rolls2 = _roll_dice(dmg_notation)
                    dmg += dmg2
                    rolls += rolls2
                dmg = max(1, dmg)
                # P0-dedup: [SKADA:]-taggen applicerade redan samma skada
                if ("skada", str(dmg)) in _skip_keys:
                    continue
                temp = hp.get("temp", 0)
                if temp > 0:
                    absorbed = min(temp, dmg)
                    hp["temp"] = temp - absorbed
                    dmg -= absorbed
                hp["current"] = max(0, hp.get("current", 1) - dmg)
                crit_str = " 💥 KRITISK!" if crit else ""
                dmg_type = atk.get("damage_type") or enemy.get("damage_type", "okänd")
                combat_log.append({
                    "round": current_round, "actor": "enemy", "name": attacker_name,
                    "text": f"träffar dig — {dmg} skada ({dmg_type}){crit_str} (🎲 d20={d20}+{attack_bonus}={total} · {dmg_notation}: [{', '.join(str(x) for x in rolls)}]={dmg})",
                })
                effects.append({
                    "type": "enemy_hit", "value": attacker_name, "damage": dmg, "crit": crit,
                    "roll": total, "d20": d20, "bonus": attack_bonus,
                    "damage_dice": dmg_notation, "damage_rolls": rolls,
                })
                logger.info("⚔️ Enemy attack: %s → spelaren, %d skada (d20=%d) → HP %d/%d", attacker_name, dmg, d20, hp["current"], hp["max"])
            else:
                # Fienden finns inte i combat-listan (t.ex. narrativ attack utanför strid) —
                # fallback till DM:s angivna utfall (gamla beteendet)
                if atk.get("hit"):
                    dmg = max(0, int(atk.get("damage", 0)))
                    if dmg > 0:
                        if ("skada", str(dmg)) in _skip_keys:
                            continue
                        temp = hp.get("temp", 0)
                        if temp > 0:
                            absorbed = min(temp, dmg)
                            hp["temp"] = temp - absorbed
                            dmg -= absorbed
                        hp["current"] = max(0, hp.get("current", 1) - dmg)
                        roll_str = f" (slag {atk.get('roll', '?')})" if atk.get("roll") else ""
                        combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"träffar dig — {dmg} skada ({atk.get('damage_type', 'okänd')}){roll_str}"})
                        effects.append({"type": "skada", "value": dmg})
                        logger.info("⚔️ Enemy attack (narrativ): %s → spelaren, %d skada → HP %d/%d", attacker_name, dmg, hp["current"], hp["max"])
                else:
                    roll_str = f" (slag {atk.get('roll', '?')})" if atk.get("roll") else ""
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"missar dig{roll_str}"})

        # Combat events → logga
        for event in mech.get("combat_events", []):
            event_str = str(event).strip()
            if event_str:
                combat_log.append({"round": current_round, "actor": "system", "name": "", "text": event_str})

        # ── Turordning (chat-first): hybrid-avancering ──
        # LLM får driva när den kan (attacker/events/combat_round), men vi har
        # ett DETERMINISTISKT skyddsnät: om något mekaniskt hände denna tur
        # (stridsloggen växte eller combat-effekter applicerades) avancerar vi
        # ändå. Utan detta fastnar rundan på 1 när Guardian inte skickar
        # player_attacks/enemy_attacks (marielle 2026-08-02: 13 turer, runda 1).
        llm_attacks = bool(
            mech.get("player_attacks") or mech.get("enemy_attacks") or mech.get("combat_events")
        )
        mechanical_this_turn = len(combat_log) > combat_log_len_before or any(
            e.get("type") in ("skada", "hela", "combat_dmg", "npc_död", "enemy_död", "combat_end")
            for e in effects
        )
        if mech.get("combat_round"):
            # LLM avancerade rundan explicit → starta den färskt
            for _t in combat.get("turn_order", []):
                _t["acted"] = False
            combat["current_index"] = 0
            combat["player_actions"] = {"action": True, "bonus": True, "reaction": True}
        elif llm_attacks or mechanical_this_turn:
            _advance_turn(combat, state)

        # Auto-avsluta strid om alla fiender döda
        if all(not e.get("alive", True) for e in combat.get("enemies", [])) and combat.get("enemies"):
            combat["active"] = False
            combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
            combat_log.append({"round": current_round, "actor": "system", "name": "", "text": "Alla fiender besegrade — striden är över"})
            effects.append({"type": "combat_end", "value": "alla besegrade"})
            logger.info("🏁 Combat over — all enemies defeated")
        else:
            # State-snapshot efter turen: ALLA deltagare inkl. spelaren med
            # nuvarande HP — så nästa turs Guardian kan jämföra och justera
            # HP/status på samtliga (krav: battle logg listar alla).
            snapshot_parts = []
            ph = ch.get("hp", {})
            snapshot_parts.append(f"{ch.get('name', 'Spelaren')} {ph.get('current', '?')}/{ph.get('max', '?')} HP")
            for e in combat.get("enemies", []):
                alive_mark = "" if e.get("alive", True) else " (död)"
                snapshot_parts.append(f"{e.get('name', '?')} {e.get('hp', '?')}/{e.get('max_hp', '?')} HP{alive_mark}")
            combat_log.append({
                "round": current_round, "actor": "system", "name": "",
                "text": "Efter turen: " + ", ".join(snapshot_parts),
                "snapshot": True,
            })

    # ── Loggbok ──
    logbook = mech.get("logbook", "")
    if logbook:
        # Shape-guard: world.logbook är Guardian-listan {day, turn, text}. Om
        # något (gammal dag-entry-kod) skrivit ett dict här → skippa istället
        # för att krascha hela appliceringen (audit 2026-08-02).
        _lb = world.get("logbook")
        if not isinstance(_lb, list):
            _lb = []
            world["logbook"] = _lb
        _lb.append({
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
        # Gör kastet VÄNTANDE via samma mekanism som DM:s [KAST:]-taggar —
        # läggs i meta.last_roll_requests så en refresh återställer knappen.
        # Rensas automatiskt när spelaren svarar med [Resultat:…].
        lr = state.setdefault("meta", {}).setdefault("last_roll_requests", [])
        lr_label = label or notation
        if not any(r.get("notation") == notation and r.get("label") == lr_label for r in lr):
            lr.append({"notation": notation, "label": lr_label})
        logger.info("🛡️ Guardian: roll_grant %s (%s)", notation, label)

    # ── Korrigeringar ──
    for corr in mech.get("corrections", []):
        field = corr.get("field", "")
        action = corr.get("action", "")
        reason = corr.get("reason", "")
        if action == "retract" and field == "items_add":
            # P0: ta bort föremålet med MATCHANDE NAMN (inte inv.pop() på sista!)
            inv = state.get("inventory", [])
            target_name = (corr.get("item_name") or "").strip()
            if not target_name:
                # Fallback: hitta föremålet via reason-texten (Guardian nämner ofta namnet)
                for it in inv:
                    if it.get("name", "").lower() in reason.lower():
                        target_name = it.get("name", "")
                        break
            removed = None
            if target_name:
                for i, it in enumerate(inv):
                    if it.get("name", "").lower() == target_name.lower():
                        removed = inv.pop(i)
                        break
            elif inv:
                # Ingen namn-träff — behåll gamla beteendet som sista utväg
                removed = inv.pop()
            if removed:
                effects.append({"type": "korrigering", "value": f"Föremål återkallat: {removed.get('name', '?')}", "reason": reason})
                logger.info("🛡️ Guardian correction: revoked '%s' — %s", removed.get("name", "?"), reason[:80])
            else:
                logger.info("🛡️ Guardian correction: could not revoke '%s' (not found)", target_name or "?")
        elif field == "npc_remove" and action == "remove":
            # Ta bort NPC(s) med matchande namn
            npcs = state.get("npcs", [])
            names_to_remove = corr.get("names", [])
            if isinstance(corr.get("name"), str):
                names_to_remove.append(corr["name"])
            for rname in names_to_remove:
                rname_lower = rname.strip().lower()
                for i, npc in enumerate(npcs):
                    if npc.get("name", "").lower() == rname_lower:
                        removed_npc = npcs.pop(i)
                        effects.append({"type": "korrigering", "value": f"NPC borttagen: {removed_npc.get('name', '?')}", "reason": reason})
                        logger.info("🛡️ Guardian korrigering: NPC '%s' borttagen — %s", removed_npc.get("name", "?"), reason[:80])
                        break
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
    logger.debug("🛡️ Guardian: NPC '%s' not found for note", name)


def _safe_int(value, default: int = 0) -> int:
    """int() utan krasch — explicit null/sträng/'None' → default."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
                "npcs_new", "npc_relations", "npc_notes", "locations_new",
                "world_lore", "roll_grants", "corrections",
                "initiative_entries", "enemy_actions", "status_apply",
                "player_attacks", "enemy_attacks", "combat_events"):
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

    # current_location: str (renad) eller None
    _cl = mech.get("current_location")
    if _cl is None or not isinstance(_cl, str) or not _cl.strip():
        mech["current_location"] = None
    else:
        mech["current_location"] = clean_location_name(_cl)

    # Stridsfält: combat_start/combat_end ska vara dict eller null,
    # combat_round ska vara int eller null
    for _ck in ("combat_start", "combat_end"):
        if mech.get(_ck) is not None and not isinstance(mech.get(_ck), dict):
            mech[_ck] = None
    if mech.get("combat_round") is not None:
        try:
            mech["combat_round"] = int(mech["combat_round"])
        except (TypeError, ValueError):
            mech["combat_round"] = None

    # day_summary: ska vara dict eller null
    ds = mech.get("day_summary")
    if ds and not isinstance(ds, dict):
        mech["day_summary"] = None

    return mech


# ═══════════════════════════════════════
# 5. BATTLE AI — Fiendernas stridshjärna
# ═══════════════════════════════════════

BATTLE_AI_SYSTEM = """\
Du är Battle AI — fiendernas stridshjärna i ett D&D 5e-rollspel.
Du bestämmer vad varje fiende gör under sin tur baserat på situationen.

## Regler
1. Varje fiende får: 1 action + 1 bonus action (valfritt) + rörelse.
2. Fiender prioriterar: attackera spelaren > använda förmåga > röra sig.
3. Låga HP (<30%) → fienden kan försöka fly eller använda desperat förmåga.
4. Flera fiender samordnar: om en kan ge fördel åt en annan, gör det.
5. Bossar (HP > 20) kan ha multiattack (2 attacker).
6. Returnera ENDAST JSON.

## Format
{
  "actions": [
    {
      "enemy": "fiendens namn",
      "type": "attack" | "spell" | "flee" | "ability" | "move",
      "target": "player" | "fiendens namn" | null,
      "attack_bonus": N,
      "damage_dice": "1d6+2",
      "description": "kort beskrivning av handlingen"
    }
  ]
}

## Exempel
Fiender: Goblin A (5/7 HP), Goblin B (7/7 HP). Spelaren: 12/20 HP, AC 13.
→ {"actions": [
  {"enemy": "Goblin A", "type": "attack", "target": "player", "attack_bonus": 4, "damage_dice": "1d6+2", "description": "Hugger med sin dolk"},
  {"enemy": "Goblin B", "type": "attack", "target": "player", "attack_bonus": 4, "damage_dice": "1d6+2", "description": "Skjuter med sin kortbåge"}
]}
"""

BATTLE_AI_SYSTEM_EN = """\
You are Battle AI — the enemy combat brain in a D&D 5e RPG.
You decide what each enemy does on their turn based on the situation.

## Rules
1. Each enemy gets: 1 action + 1 bonus action (optional) + movement.
2. Enemies prioritize: attack player > use ability > move.
3. Low HP (<30%) → enemy may flee or use desperate ability.
4. Multiple enemies coordinate: if one can give advantage to another, do it.
5. Bosses (HP > 20) may have multiattack (2 attacks).
6. Return ONLY JSON.

## Format
{
  "actions": [
    {
      "enemy": "enemy name",
      "type": "attack" | "spell" | "flee" | "ability" | "move",
      "target": "player" | "enemy name" | null,
      "attack_bonus": N,
      "damage_dice": "1d6+2",
      "description": "short description of the action"
    }
  ]
}
"""


async def battle_ai_decide(
    state: dict,
    model_call_fn: ModelCallFn,
    language: str = "sv",
) -> list[dict]:
    """Battle AI: Bestäm alla fienders handlingar för denna runda.

    Returnerar lista av action-dicts:
    [{"enemy": "Goblin", "type": "attack", "target": "player",
      "attack_bonus": 4, "damage_dice": "1d6+2", "description": "..."}]
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return []

    char = state.get("character", {})
    hp = char.get("hp", {})
    player_ac = char.get("ac", 10)
    player_name = char.get("name", "Spelaren")

    enemies = [e for e in combat.get("enemies", []) if e.get("alive", True)]
    if not enemies:
        return []

    # Bygg kontext
    enemy_lines = []
    for e in enemies:
        status_str = ""
        if e.get("statuses"):
            status_str = " [" + ", ".join(s["name"] for s in e["statuses"]) + "]"
        enemy_lines.append(
            f"- {e['name']}: {e['hp']}/{e['max_hp']} HP, AC {e['ac']}, "
            f"attack +{e.get('attack_bonus', 3)}, damage {e.get('damage_dice', '1d6+1')}{status_str}"
        )

    if language == "en":
        system = BATTLE_AI_SYSTEM_EN
        user_msg = (
            f"## Player\n{player_name}: {hp.get('current', '?')}/{hp.get('max', '?')} HP, AC {player_ac}\n\n"
            f"## Enemies\n" + "\n".join(enemy_lines) + "\n\n"
            f"## Round {combat.get('round', 1)}\n"
            "Decide what each enemy does this round:"
        )
    else:
        system = BATTLE_AI_SYSTEM
        user_msg = (
            f"## Spelaren\n{player_name}: {hp.get('current', '?')}/{hp.get('max', '?')} HP, AC {player_ac}\n\n"
            f"## Fiender\n" + "\n".join(enemy_lines) + "\n\n"
            f"## Runda {combat.get('round', 1)}\n"
            "Bestäm vad varje fiende gör denna runda:"
        )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw = await model_call_fn(messages)
    except Exception as e:
        logger.warning("⚔️ Battle AI misslyckades: %s", e)
        return _fallback_enemy_actions(enemies)

    result = _parse_json(raw)
    if not result or not isinstance(result.get("actions"), list):
        logger.warning("⚔️ Battle AI: ogiltig JSON → fallback")
        return _fallback_enemy_actions(enemies)

    actions = result["actions"]
    # Validera: bara levande fiender
    alive_names = {e["name"].lower() for e in enemies}
    valid = [a for a in actions if isinstance(a, dict) and a.get("enemy", "").lower() in alive_names]

    if not valid:
        return _fallback_enemy_actions(enemies)

    logger.info("⚔️ Battle AI: %d fiendeaktioner", len(valid))
    return valid


def _fallback_enemy_actions(enemies: list[dict]) -> list[dict]:
    """Fallback om Battle AI misslyckas: alla fiender attackerar."""
    return [
        {
            "enemy": e["name"],
            "type": "attack",
            "target": "player",
            "attack_bonus": e.get("attack_bonus", 3),
            "damage_dice": e.get("damage_dice", "1d6+1"),
            "description": "Attackerar spelaren",
        }
        for e in enemies if e.get("alive", True)
    ]


def apply_enemy_actions(state: dict, actions: list[dict]) -> list[dict]:
    """Applicera Battle AI:s fiendeaktioner på state.

    Varje action: {"enemy": str, "type": str, "target": str,
                   "attack_bonus": int, "damage_dice": str, "description": str}

    Returnerar effects-lista för frontend.
    """
    from combat import roll_dice, roll_d20, add_status, has_disadvantage

    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return []

    char = state.get("character", {})
    player_ac = int(char.get("ac", 10))
    player_name = char.get("name", "Spelaren")
    effects: list[dict] = []

    for action in actions:
        enemy_name = action.get("enemy", "")
        action_type = action.get("type", "attack")
        enemy = next(
            (e for e in combat.get("enemies", [])
             if e.get("name", "").lower() == enemy_name.lower() and e.get("alive", True)),
            None,
        )
        if not enemy:
            continue

        if action_type == "flee":
            enemy["alive"] = False  # flyr = lämnar striden
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "enemy",
                "name": enemy["name"], "text": "flyr från striden",
            })
            effects.append({"type": "enemy_fled", "value": enemy["name"]})
            logger.info("🏃 %s flees from combat", enemy["name"])
            continue

        if action_type in ("attack", "spell", "ability"):
            # Rulla attack mot spelarens AC
            d20 = roll_d20()
            disadv = has_disadvantage(enemy)
            if disadv:
                d20 = min(d20, roll_d20())

            attack_bonus = int(action.get("attack_bonus", enemy.get("attack_bonus", 3)))
            total = d20 + attack_bonus
            hit = total >= player_ac or d20 == 20
            crit = d20 == 20
            fumble = d20 == 1

            if fumble:
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "enemy",
                    "name": enemy["name"],
                    "text": f"missar {player_name} (nat 1!)",
                })
                effects.append({"type": "enemy_miss", "value": enemy["name"], "roll": total, "d20": d20, "bonus": attack_bonus})
            elif hit:
                dmg_notation = action.get("damage_dice", enemy.get("damage_dice", "1d6+1"))
                dmg, rolls = roll_dice(dmg_notation)
                if crit:
                    dmg2, rolls2 = roll_dice(dmg_notation)
                    dmg += dmg2
                    rolls += rolls2
                dmg = max(1, dmg)

                hp = char.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
                temp = hp.get("temp", 0)
                if temp > 0:
                    absorbed = min(temp, dmg)
                    hp["temp"] = temp - absorbed
                    dmg -= absorbed
                hp["current"] = max(0, hp.get("current", 1) - dmg)

                desc = action.get("description", "")
                log_text = f"träffar {player_name} — {dmg} skada"
                if crit:
                    log_text += " (KRITISK!)"
                if desc:
                    log_text += f" ({desc})"
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "enemy",
                    "name": enemy["name"], "text": log_text,
                })
                effects.append({
                    "type": "enemy_hit", "value": enemy["name"],
                    "damage": dmg, "crit": crit, "roll": total,
                    "d20": d20, "bonus": attack_bonus,
                    "damage_dice": dmg_notation, "damage_rolls": rolls,
                })
                logger.info("⚔️ %s → %s: %d skada (AC %d)", enemy["name"], player_name, dmg, player_ac)
            else:
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "enemy",
                    "name": enemy["name"],
                    "text": f"missar {player_name} (slag {total} mot AC {player_ac})",
                })
                effects.append({"type": "enemy_miss", "value": enemy["name"], "roll": total, "d20": d20, "bonus": attack_bonus})

    # Auto-avsluta om alla fiender döda/flydde
    if all(not e.get("alive", True) for e in combat.get("enemies", [])):
        from combat import end_combat
        end_combat(state, "alla fiender besegrade eller flydde")
        effects.append({"type": "combat_end", "value": "alla besegrade"})
    else:
        # State-snapshot efter Battle AI-turen: ALLA deltagare inkl. spelaren
        # med nuvarande HP — så nästa tur kan Guardian jämföra och justera
        # HP/status på samtliga (krav: battle logg listar alla).
        snapshot_parts = []
        ph = char.get("hp", {})
        snapshot_parts.append(f"{player_name} {ph.get('current', '?')}/{ph.get('max', '?')} HP")
        for e in combat.get("enemies", []):
            alive_mark = "" if e.get("alive", True) else " (död)"
            snapshot_parts.append(f"{e.get('name', '?')} {e.get('hp', '?')}/{e.get('max_hp', '?')} HP{alive_mark}")
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "system", "name": "",
            "text": "Efter turen: " + ", ".join(snapshot_parts),
            "snapshot": True,
        })

    return effects


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
            # P2-fix: undvik dubbel-relation ("fiende, fiende") när roll och
            # relation är samma ord, och översätt relationen i EN-läge.
            if en:
                _rel_en = {"allierad": "ally", "neutral": "neutral", "fiende": "enemy", "okänd": "unknown"}
                relation = _rel_en.get(str(relation).lower(), relation)
            meta = f"{role}, {relation}" if str(role).lower() != str(relation).lower() else role
            if en:
                lines.append(f"🧙 **New character:** {v} ({meta})")
            else:
                lines.append(f"🧙 **Ny gestalt:** {v} ({meta})")
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
        elif t == "flytt":
            if en:
                lines.append(f"📍 **You are now at:** {v}")
            else:
                lines.append(f"📍 **Du är nu i:** {v}")
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
        elif t == "combat_start":
            lines.append(f"⚔ **{'Combat begins!' if en else 'STRIDEN BÖRJAR'}** — {v}")
        elif t == "combat_dmg":
            amt = e.get("amount", "?")
            if en:
                lines.append(f"💔 **{v}** takes {amt} damage")
            else:
                lines.append(f"💔 **{v}** tar {amt} skada")
        elif t == "combat_round":
            lines.append(f"⚔ **{'Round' if en else 'Runda'} {v}**")
        elif t == "enemy_död":
            if en:
                lines.append(f"💀 **{v} falls!**")
            else:
                lines.append(f"💀 **{v} faller!**")
        elif t == "initiativ":
            label = "Initiative" if en else "Initiativ"
            lines.append(f"🎲 **{label}:** {v}")
        elif t == "combat_end":
            if en:
                lines.append(f"🏁 **Combat over — {v}**")
            else:
                lines.append(f"🏁 **Striden är över — {v}**")
        elif t == "enemy_hit":
            dmg = e.get("damage", "?")
            crit = e.get("crit", False)
            roll = e.get("roll", "?")
            crit_str = f" {'💥 CRIT!' if crit else ''}"
            if en:
                lines.append(f"🗡️ **{v}** hits you — **{dmg} damage**{crit_str} (roll {roll})")
            else:
                lines.append(f"🗡️ **{v}** träffar dig — **{dmg} skada**{crit_str} (slag {roll})")
        elif t == "enemy_miss":
            roll = e.get("roll", "?")
            if en:
                lines.append(f"🛡️ **{v}** misses you (roll {roll})")
            else:
                lines.append(f"🛡️ **{v}** missar dig (slag {roll})")
        elif t == "enemy_fled":
            if en:
                lines.append(f"🏃 **{v}** flees the battle!")
            else:
                lines.append(f"🏃 **{v}** flyr från striden!")
        elif t == "status_dmg":
            status = e.get("status", "?")
            amt = e.get("amount", "?")
            if en:
                lines.append(f"☠️ **{status}** deals {amt} damage")
            else:
                lines.append(f"☠️ **{status}** ger {amt} skada")
        elif t == "status_end":
            status = e.get("status", "?")
            if en:
                lines.append(f"✨ **{status}** wears off")
            else:
                lines.append(f"✨ **{status}** avtar")
        elif t == "dödsräddning":
            label = "Death save" if en else "Dödsräddning"
            lines.append(f"💀 **{label}:** {v}")
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
        # P2-fix: time_passed är ett dict {hours, description} — formatera det
        # istället för att dumpa rå Python-dict i chatten.
        if isinstance(time_passed, dict):
            hours = time_passed.get("hours") or 0
            desc = (time_passed.get("description") or "").strip()
            if desc and hours:
                tp_str = f"{desc} ({hours}h)"
            elif desc:
                tp_str = desc
            else:
                tp_str = f"{hours}h"
        else:
            tp_str = str(time_passed)
        lines.append(f"🕐 **{tp_label}:** {tp_str}")

    rest = mech.get("rest")
    if rest:
        kind = rest.get("kind") if isinstance(rest, dict) else rest
        if kind == "long":
            lines.append("🏕️ **Lång vila** — HP återställd" if not en else "🏕️ **Long rest** — HP restored")
        elif kind == "short":
            vila = next((e.get("detail", "") for e in effects if e.get("type") == "vila"), "")
            if vila:
                lines.append(f"⛺ **Kort vila:** {vila}" if not en else f"⛺ **Short rest:** {vila}")
            else:
                lines.append("⛺ **Kort vila**" if not en else "⛺ **Short rest**")

    # ── Maskinläsbara taggar för frontend (parsas och tas bort ur visningen) ──
    tags = []
    for e in effects:
        if e.get("type") == "roll_grant":
            notation = e.get("notation", "")
            label = e.get("value", "")
            if notation:
                tags.append(f"[ROLL_GRANT:{notation}|{label}]")

    # ── [COMBAT:]-taggen (Krigsrådet) — skickas BARA när combat ändrats ──
    # Frontend parsar taggen, uppdaterar panelen och tar bort den ur texten.
    # Måste vara SIST i meddelandet (frontend-regex: /\[COMBAT:([^\]]*)\]\s*$/).
    combat = state.get("world", {}).get("combat")
    if combat:
        _changed = bool(
            {e.get("type") for e in effects}
            & {"combat_start", "combat_dmg", "combat_round", "enemy_död", "initiativ", "combat_end", "skada", "hela"}
        ) or any(mech.get(k) for k in ("combat_start", "combat_round", "initiative_entries", "combat_end"))
        _just_ended = combat.get("active") is False and combat.get("ended_turn") == state.get("meta", {}).get("turn_count", 0)
        if _changed or _just_ended:
            # Include player HP so the frontend status bar + inline messages can show it
            ch = state.get("character", {})
            php = ch.get("hp", {})
            combat_for_tag = dict(combat)
            combat_for_tag["player_hp"] = {"current": php.get("current", 0), "max": php.get("max", 0)}
            _ct = _combat_tag(combat_for_tag)
            if _ct:
                tags.append(_ct)

    if not lines:
        # Inga synliga rader — skicka bara taggarna (frontend döljer dem)
        return "".join(tags) if tags else ""

    turn_label = f" · {('Turn' if en else 'Tur')} {turn}" if turn else ""
    header = "🦉 **Lorekeeper**" + turn_label

    return header + "\n" + "\n".join(lines) + ("\n" + "".join(tags) if tags else "")
