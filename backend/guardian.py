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
import re
import secrets
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

logger = logging.getLogger("loreweavers.guardian")

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
8. När handlingen matchar en skill karaktären är skicklig i (proficient), inkludera proficiency-bonusen i notationen och använd skill-namnet som label (STEALTH, PERCEPTION, ATHLETICS…).
9. Mörker (5e, P2): om scenen är mörk och karaktären SAKNAR darkvision (se kontext) → sätt NACKDEL på perception- och attackrullar. Med darkvision 60 ft → normala rullar i dunkel.

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
8. When the action maps to a skill the character is proficient in, include the proficiency bonus in the notation and use the skill name as the label (STEALTH, PERCEPTION, ATHLETICS…).
9. Darkness (5e, P2): if the scene is dark and the character LACKS darkvision (see context) → set DISADVANTAGE on perception and attack rolls. With darkvision 60 ft → normal rolls in dim light.

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

# De 18 standard-5e-skillsen (P0-1) — {name, ability}. Proficient-fylls av
# _ensure_skills. Engelska namn (UI är alltid engelsk för skills).
_STANDARD_SKILLS = [
    {"name": "Athletics", "ability": "STR"},
    {"name": "Acrobatics", "ability": "DEX"},
    {"name": "Sleight of Hand", "ability": "DEX"},
    {"name": "Stealth", "ability": "DEX"},
    {"name": "Arcana", "ability": "INT"},
    {"name": "History", "ability": "INT"},
    {"name": "Investigation", "ability": "INT"},
    {"name": "Nature", "ability": "INT"},
    {"name": "Religion", "ability": "INT"},
    {"name": "Animal Handling", "ability": "WIS"},
    {"name": "Insight", "ability": "WIS"},
    {"name": "Medicine", "ability": "WIS"},
    {"name": "Perception", "ability": "WIS"},
    {"name": "Survival", "ability": "WIS"},
    {"name": "Deception", "ability": "CHA"},
    {"name": "Intimidation", "ability": "CHA"},
    {"name": "Performance", "ability": "CHA"},
    {"name": "Persuasion", "ability": "CHA"},
]


def _ensure_skills(ch: dict) -> list[dict]:
    """Fyll character.skills med de 18 standard-5e-skillsen om de saknas/tomma.

    Befintliga skills behålls (med sina proficient-flaggor); saknade
    standard-skills läggs till med proficient: False. Returnerar listan.
    """
    skills = ch.setdefault("skills", [])
    if not isinstance(skills, list):
        skills = []
        ch["skills"] = skills
    existing = {s.get("name", "").lower() for s in skills if isinstance(s, dict)}
    for std in _STANDARD_SKILLS:
        if std["name"].lower() not in existing:
            skills.append({
                "name": std["name"],
                "ability": std["ability"],
                "proficient": False,
            })
            existing.add(std["name"].lower())
    return skills


def _skill_bonus(ch: dict, skill: dict) -> int:
    """5e-skill-bonus = ability-mod + proficiency om skicklig (proficient)."""
    ability = skill.get("ability", "")
    abil_mod = _ability_mod(ch, ability) if ability else 0
    if skill.get("proficient"):
        abil_mod += int(ch.get("proficiency", 2) or 0)
    return abil_mod


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
    hp = ch.get("hp") or {}
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

    # Skills (5e, P0-1): bonus = ability-mod + proficiency om proficient (●)
    skills = _ensure_skills(ch)
    if skills:
        skill_parts = []
        for s in skills:
            bonus = _skill_bonus(ch, s)
            mark = " ●" if s.get("proficient") else ""
            skill_parts.append(
                f"{s.get('name', '?')} {bonus:+d} ({s.get('ability', '?')}){mark}"
            )
        parts.append("Skills: " + ", ".join(skill_parts))

    # Resistans/sårbarhet/immunitet (5e, P2)
    _res = ch.get("resistances") or []
    _vul = ch.get("vulnerabilities") or []
    _imm = ch.get("immunities") or []
    if _res or _vul or _imm:
        bits = []
        if _res:
            bits.append("resistant: " + ", ".join(str(x) for x in _res))
        if _vul:
            bits.append("vulnerable: " + ", ".join(str(x) for x in _vul))
        if _imm:
            bits.append("immune: " + ", ".join(str(x) for x in _imm))
        parts.append("Damage: " + "; ".join(bits))

    # Darkvision (5e, P2)
    _dv = ch.get("darkvision")
    if _dv:
        parts.append(f"Darkvision: {_dv}")
    else:
        parts.append("Darkvision: none — darkness imposes DISADVANTAGE on perception/attack rolls")

    # Exhaustion (5e, P2) — aktiva straff
    _exh = int(ch.get("exhaustion", 0) or 0)
    if _exh > 0:
        pen = _EXHAUSTION_PENALTIES.get(_exh, "")
        parts.append(f"⚠ EXHAUSTION level {_exh}: {pen}")

    # Encumbrance (5e, P2) — aktiv belastning
    _enc = ch.get("_encumb") or _encumbrance_level(ch, 0.0)
    if _enc == "light":
        parts.append("⚠ Encumbered (light): speed −10 ft, disadvantage on STR/DEX checks")
    elif _enc == "heavy":
        parts.append("⚠ Encumbered (heavy): speed −20 ft, disadvantage on STR/DEX/CON checks and attack rolls")
    elif _enc == "overload":
        parts.append("⚠ OVERLOADED: speed 0 — cannot move")

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

### Besvärjelser (spells)
- spells_add: Besvärjelser karaktären LÄR SIG (via level-up, scroll, undervisning eller DM-belöning). Ange: [{\"name\": \"Eldklot\", \"level\": 3, \"school\": \"evocation\", \"casting_time\": \"1 action\", \"damage_dice\": \"8d6\", \"description\": \"...\"}]. Cantrips = level 0. Lägg ENDAST till spells som faktiskt tilldelas i narrationen. Om karaktären är en kasterklass (wizard, sorcerer, cleric, druid, bard, warlock) och SAKNAR spells helt, extrahera passande klassbesvärjelser (minst 2 cantrips + 2 nivå-1) så karaktärsbladet aldrig är tomt.
- spell_slots_spend: När spelaren kastar en besvärjelse på nivå 1+ (INTE cantrip). Ange name + level: [{\"name\": \"Eldklot\", \"level\": 2}]. KODEN minskar spell_slots.current — fyll INTE i remaining själv.

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
- npcs_near: NPCs som JUST NU befinner sig i spelarens direkta närhet — samma rum, synhåll \
  eller pågående konversation. Ange EXAKTA namn (array). Tom lista om ingen är nära. \
  Uppdatera VARJE tur: när en NPC lämnar närheten försvinner den ur listan.
- npc_notes: Nya anteckningar om NPCs (personlighet, mål, hemligheter, utseende). \
  DETEKTERA NAMNAVSLÖJANDEN: om en "okänd" NPC får ett namn, eller om en NPC:s \
  identitet/roll avslöjas ("den gamle mannen visar sig vara..."), uppdatera notes.
- npc_name_reveals: Om en NPC:s sanna namn eller identitet avslöjas. \
  Ange old_name (eller "okänd"), new_name, och reveal_text (vad som avslöjades).

### Karaktärsuppdateringar
- character_updates: Om spelarens karaktär lär sig något nytt, upptäcker en förmåga, \
  eller om bakgrundshistorien utvecklas. Ange field (t.ex. "trait", "backstory", "ability") \
  och text (beskrivning av vad som ändrades).
- Features: character_updates kan lägga till features vid level-up; features ska vara {name, level, description}.

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
  KRITISKT: när spelaren vilar (säger "long rest", "lång vila", "sleep", "sova",
  "camp", "till imorgon", "recharge my spells"…) MÅSTE du sätta rest — annars
  återställs inget mekaniskt! En lång vila (8h) återställer automatiskt full HP,
  alla spell slots och hit dice. Sätt INTE bara time_passed/new_day för vila —
  vila kräver rest-fältet (time_passed är för tid som förflyter, t.ex. resor).
- new_day: Om en ny dag börjar. Ange description.

### Strid (chat-first combat)
- combat_start: Om en strid BÖRJAR i denna narration. Ange enemies: [{"name": "...", "hp": N, "ac": N, "max_hp": N}].
- combat_round: Om DM:n anger en ny runda ("Runda 2", "Next round"), sätt rundnumret (heltal).
- player_attacks: Spelarens attacker som DM narrerar. Ange: [{"target": "fiendnamn", "hit": true/false, "damage": N, "damage_type": "slashing", "crit": false}]. Extrahera ENDAST om DM explicit beskriver att spelaren träffar/missar och anger skada.
- ally_attacks: Allierades attacker (vänliga NPC:er som kämpar VID SPELARENS SIDA — se "Allierade" i stridstillståndet). Ange: [{"ally": "Mimmrick", "target": "goblin", "hit": true/false, "damage": N, "roll": N, "damage_type": "slashing", "crit": false}]. Extrahera ENDAST om DM beskriver den allierades attack med slag och skada. Minska fiendens HP.
- ally_damage: Skada som allierade TAR från fiender. Ange: [{"ally": "Mimmrick", "amount": N, "attacker": "goblin", "damage_type": "piercing"}]. Vid dödlig skada dör den allierade.
- enemy_attacks: Fiendernas attacker i denna tur. Ange ENDAST attackeraren (+ valfri damage_type om DM nämner vapen): [{"attacker": "goblin", "damage_type": "piercing"}]. KODEN rullar tärningen (d20 + attack_bonus mot spelarens AC) och skadan — fyll INTE i hit/damage/roll själv. Om DM:narrationen säger att fienden träffar/missar, ignorera det — koden bestämmer utfallet.
- status_apply: När narrationen entydigt ger en status/villkor: [{"name": "prone|restrain|stun|blind|poison|burn|bleed|frighten|charm", "target": "spelarnamn|fiendens namn|allierades namn", "duration": 2}]. "target": "player" = spelaren. KODEN applicerar mekaniken (prone/restrain/blind ger nackdel på attackerarens egna slag och fördel på motståndarens; stun hoppar över tur; poison/burn/bleed gör skada per runda). Ange ENDAST om DM:n beskriver tillståndet uttryckligen ("faller omkull", "bunden i rankor", "förgiftad").
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

### Inspiration (5e)
- inspiration_gain: Sätt true när DM belönar heroiska/smarta/rollspelstarka handlingar — karaktären får inspiration (en gång åt gången).
- inspiration_spend: Sätt true när spelaren spenderar sin inspiration för ADVANTAGE på ett kast. Används bara om karaktären faktiskt har inspiration.

### Exhaustion (5e, P2)
- exhaustion_change: heltal (positivt = öka, negativt = minska). Källa: svält, törst, iskyla, sömnbrist, överansträngning. Nivåer 1-6 (1=disadvantage på ability checks, 2=speed halverad, 3=disadvantage på attacker/saves, 4=HP max halverad, 5=speed 0, 6=död). Lång vila sänker automatiskt med 1 — ange INTE negativt vid vila.

### Cover (5e, P2)
- cover_set: När spelaren tar skydd — {"target": "player", "cover": "half"|"three_quarters"|"full"|null}. half = +2 AC mot attacker, three_quarters = +5 AC, full = kan inte träffas. KODEN lägger bonusen på fiendens träffchans — fyll INTE i AC själv.

### Träning / Downtime (5e, P2)
- training_update: lägg till dagar på downtime-träning — [{\"name\": \"Stealth\", \"days\": 2}]. När träningen når sitt mål (10 dagar för skills) ger KODEN proficiency automatiskt.

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
  "spells_add": [],
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
  "ally_attacks": [],
  "ally_damage": [],
  "enemy_attacks": [],
  "status_apply": [],
  "combat_events": [],
  "roll_grants": [],
  "spell_slots_spend": [],
  "inspiration_gain": false,
  "inspiration_spend": false,
  "exhaustion_change": 0,
  "cover_set": null,
  "training_update": [],
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
    hp = ch.get("hp") or {}
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

    # Skills (5e, P0-1) — kompakt rad: alla listade skills, proficient markerade
    skills = _ensure_skills(ch)
    if skills:
        skill_str = ", ".join(
            f"{s.get('name', '?')}{' ●' if s.get('proficient') else ''}"
            for s in skills
        )
        parts.append(f"Skills: {skill_str}")

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

    # P2-kontext (5e): resistans, exhaustion, darkvision, träning, cover
    _res = ch.get("resistances") or []
    _vul = ch.get("vulnerabilities") or []
    _imm = ch.get("immunities") or []
    if _res or _vul or _imm:
        parts.append(f"Damage: R[{', '.join(str(x) for x in _res)}] V[{', '.join(str(x) for x in _vul)}] I[{', '.join(str(x) for x in _imm)}]")
    _exh = int(ch.get("exhaustion", 0) or 0)
    if _exh > 0:
        parts.append(f"Exhaustion: L{_exh} ({_EXHAUSTION_PENALTIES.get(_exh, '')})")
    if ch.get("darkvision"):
        parts.append(f"Darkvision: {ch['darkvision']}")
    training = ch.get("training") or []
    if training:
        parts.append("Training: " + ", ".join(f"{t.get('name','?')} {t.get('days_spent',0)}/{t.get('days_needed',10)}d" for t in training[:5]))
    _combat2 = state.get("world", {}).get("combat")
    if _combat2 and _combat2.get("player_cover"):
        _cv_label = {"half": "+2 AC", "three_quarters": "+5 AC", "full": "untargetable"}.get(_combat2["player_cover"], _combat2["player_cover"])
        parts.append(f"Cover: {_combat2['player_cover']} ({_cv_label})")

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
        hp = ch.get("hp") or {}
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
        for a in combat.get("allies", []):
            if a.get("alive", True):
                status = ", ".join(a.get("statuses", [])) if a.get("statuses") else ""
                parts.append(f"  - ALLIERAD {a.get('name', '?')} (HP {a.get('hp', '?')}/{a.get('max_hp', '?')}, AC {a.get('ac', '?')}){(' [' + status + ']') if status else ''}")
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
        "items_add": [], "items_remove": [], "currency": [], "spells_add": [],
        "quests_new": [], "quests_completed": [], "quests_failed": [],
        "npcs_new": [], "npc_relations": [], "npcs_near": [], "npc_notes": [],
        "npc_name_reveals": [], "character_updates": [],
        "locations_new": [], "current_location": None, "world_lore": [], "time_passed": None, "rest": None,
        "new_day": None, "day_summary": None, "logbook": "",
        "combat_start": None, "combat_round": None,
        "initiative_entries": [], "combat_end": None,
        "player_attacks": [], "ally_attacks": [], "ally_damage": [], "enemy_attacks": [], "combat_events": [],
        "enemy_actions": [], "status_apply": [], "roll_grants": [], "corrections": [],
        "spell_slots_spend": [], "inspiration_gain": False, "inspiration_spend": False,
        "exhaustion_change": 0, "cover_set": None, "training_update": [],
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
                "Guardian post-DM: invalid JSON (attempt %d). Raw: %.200s",
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
            "🛡️ Guardian post-DM (turn %d): %d mechanical changes (attempt %d)",
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

# Spell slots per nivå (D&D 5e) — enkel modell: ETT slot-pool {current, max}.
# Full-casters får 1:a-nivå slots enligt 5e-tabellen (2/3/4/4/4...). Warlock
# (Pact Magic): 1/2/2/2/2... Icke-kasterklasser får inga (0). (fix 2026-08-10:
# level-up uppdaterade ALDRIG spell_slots.max → level 3 wizard fastnade på 2 slots.)
_SPELL_SLOTS_BY_LEVEL = {
    "bard": {1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4},
    "cleric": {1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4},
    "druid": {1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4},
    "sorcerer": {1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4},
    "wizard": {1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4},
    "warlock": {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 10: 2, 11: 3, 12: 3, 13: 3, 14: 3, 15: 3, 16: 3, 17: 4, 18: 4, 19: 4, 20: 4},
}

# Klass-alias (SV/EN-varianter) → kanonisk nyckel. Fallback: direkt nyckel.
_CLASS_ALIASES = {
    "barbarian": "barbarian", "barbar": "barbarian",
    "bard": "bard", "skald": "bard",
    "cleric": "cleric", "präst": "cleric", "prast": "cleric", "klerk": "cleric",
    "druid": "druid",
    "fighter": "fighter", "krigare": "fighter", "stridare": "fighter",
    "monk": "monk", "munk": "monk",
    "paladin": "paladin", "riddare": "paladin",
    "ranger": "ranger", "jägare": "ranger", "jagare": "ranger", "vandrare": "ranger",
    "rogue": "rogue", "tjuv": "rogue", "lönnmördare": "rogue",
    "sorcerer": "sorcerer", "sorceress": "sorcerer",
    "warlock": "warlock", "häxmästare": "warlock", "haxmastare": "warlock",
    "wizard": "wizard", "magiker": "wizard", "trollkarl": "wizard",
}

# Klassfeatures vid level-up (D&D 5e, 2026-08-08) — kompakt tabell:
# klass → nivå → [(namn, beskrivning)]. Bara ikoniska features; Guardian kan
# komplettera fritt via character_updates. Nivå 1-5 för alla, 6-10 för vanligaste.
_CLASS_FEATURES = {
    "barbarian": {
        1: [("Rage", "Enter a rage: advantage on STR checks/saves, +2 melee damage, resistance to bludgeoning/piercing/slashing.")],
        2: [("Reckless Attack", "Attack with advantage — but enemies attack you with advantage until your next turn.")],
        3: [("Primal Path", "Choose a primal path (Berserker/Totem Warrior) and gain its signature ability.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Extra Attack", "Attack twice when you take the Attack action.")],
        6: [("Path Feature", "Gain a new ability from your primal path.")],
        7: [("Feral Instinct", "Advantage on initiative; cannot be surprised while conscious.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Brutal Critical", "Roll one additional damage die on a critical hit.")],
        10: [("Path Feature", "Gain a new ability from your primal path.")],
    },
    "bard": {
        1: [("Bardic Inspiration", "Grant an ally a d6 to add to one d20 roll.")],
        2: [("Jack of All Trades", "Add half your proficiency bonus to ability checks you're not proficient in."), ("Song of Rest", "Allies regain an extra 1d6 HP on a short rest.")],
        3: [("Bard College", "Choose a college (Lore/Valor) granting expertise and signature features.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Font of Inspiration", "Bardic Inspiration returns after a short rest.")],
        6: [("Countercharm", "Grant allies advantage against being charmed or frightened.")],
        7: [("College Feature", "Gain a new ability from your bard college.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Song of Rest", "Song of Rest dice improves to 1d8.")],
        10: [("Expertise", "Double proficiency bonus in two more skills."), ("Magical Secrets", "Learn spells from any class.")],
    },
    "cleric": {
        1: [("Spellcasting", "Cast cleric spells using your holy symbol."), ("Divine Domain", "Choose a domain granting domain spells and features.")],
        2: [("Channel Divinity", "Use your domain's divine ability once per short rest.")],
        3: [("Domain Feature", "Gain a new ability from your divine domain.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Destroy Undead", "Undead of CR 1/2 or lower are destroyed when you channel divinity.")],
        6: [("Channel Divinity", "Channel Divinity now recharges on a short rest.")],
        7: [("Domain Feature", "Gain a new ability from your divine domain.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1."), ("Destroy Undead", "Destroy Undead now affects CR 1 undead.")],
        9: [("Domain Feature", "Gain a new ability from your divine domain.")],
        10: [("Divine Intervention", "Call upon your deity for a miracle — the DM decides.")],
    },
    "druid": {
        1: [("Druidic", "Speak the secret druidic language."), ("Wild Shape", "Transform into a beast you've seen (CR 1/4 or lower, no flying/swimming).")],
        2: [("Wild Shape", "Wild Shape now allows CR 1/2 beasts and swimming.")],
        3: [("Druid Circle", "Choose a circle (Land/Moon) granting circle features.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1."), ("Wild Shape", "Wild Shape now allows CR 1 beasts.")],
        5: [("Wild Shape", "Wild Shape now allows flying beasts.")],
        6: [("Circle Feature", "Gain a new ability from your druid circle.")],
        7: [("Wild Shape", "Wild Shape now allows CR 2 beasts.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Wild Shape", "Wild Shape now allows CR 3 beasts.")],
        10: [("Circle Feature", "Gain a new ability from your druid circle.")],
    },
    "fighter": {
        1: [("Fighting Style", "Choose a fighting style (Archery, Defense, Dueling, Great Weapon Fighting, Two-Weapon Fighting)."), ("Second Wind", "Regain 1d10 + fighter level HP once per short rest.")],
        2: [("Action Surge", "Take one additional action on your turn once per short rest.")],
        3: [("Martial Archetype", "Choose an archetype (Champion/Battle Master/Eldritch Knight).")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Extra Attack", "Attack twice when you take the Attack action.")],
        6: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        7: [("Archetype Feature", "Gain a new ability from your martial archetype.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Indomitable", "Reroll a failed saving throw once per long rest.")],
        10: [("Archetype Feature", "Gain a new ability from your martial archetype.")],
    },
    "monk": {
        1: [("Unarmored Defense", "AC = 10 + DEX + WIS when unarmored."), ("Martial Arts", "Use DEX for unarmed strikes; bonus unarmed attack.")],
        2: [("Ki", "Use ki points for special abilities (Flurry of Blows, Patient Defense, Step of the Wind).")],
        3: [("Monastic Tradition", "Choose a tradition and gain its features."), ("Deflect Missiles", "Deflect ranged weapon attacks; spend 1 ki to throw back.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1."), ("Slow Fall", "Reduce falling damage using your reaction.")],
        5: [("Extra Attack", "Attack twice when you take the Attack action."), ("Stunning Strike", "Spend 1 ki to attempt to stun a creature you hit.")],
        6: [("Ki-Empowered Strikes", "Unarmed strikes count as magical."), ("Tradition Feature", "Gain a new ability from your monastic tradition.")],
        7: [("Evasion", "Take no damage on successful DEX saves, half on failure.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Unarmored Movement", "Movement speed increases by 10 ft.")],
        10: [("Purity of Body", "Immune to disease and poison.")],
    },
    "paladin": {
        1: [("Lay on Hands", "Heal allies for a pool of HP equal to 5 × paladin level."), ("Divine Sense", "Sense celestials, fiends, and undead within 60 ft.")],
        2: [("Divine Smite", "Spend a spell slot to add radiant damage on a hit."), ("Fighting Style", "Choose a fighting style.")],
        3: [("Sacred Oath", "Swear an oath and gain oath features + oath spells.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Extra Attack", "Attack twice when you take the Attack action.")],
        6: [("Aura of Protection", "You and allies within 10 ft add your CHA modifier to saving throws.")],
        7: [("Oath Feature", "Gain a new ability from your sacred oath.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Oath Feature", "Gain a new ability from your sacred oath.")],
        10: [("Aura of Courage", "You and allies within 10 ft cannot be frightened.")],
    },
    "ranger": {
        1: [("Favored Enemy", "Choose a favored enemy type: advantage on tracking and recalling lore."), ("Natural Explorer", "Move stealthily while traveling and never get lost in your favored terrain.")],
        2: [("Fighting Style", "Choose a fighting style."), ("Spellcasting", "Cast ranger spells using your wisdom.")],
        3: [("Ranger Conclave", "Choose a conclave and gain its features.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Extra Attack", "Attack twice when you take the Attack action.")],
        6: [("Favored Enemy", "Choose a second favored enemy; gain a new language.")],
        7: [("Conclave Feature", "Gain a new ability from your ranger conclave.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Conclave Feature", "Gain a new ability from your ranger conclave.")],
        10: [("Hide in Plain Sight", "Hide even when only lightly obscured.")],
    },
    "rogue": {
        1: [("Sneak Attack", "Add 1d6 sneak attack damage when you attack with advantage or an ally is adjacent."), ("Thieves' Cant", "Speak a secret thieves' language.")],
        2: [("Cunning Action", "Dash, Disengage, or Hide as a bonus action.")],
        3: [("Roguish Archetype", "Choose an archetype (Thief/Assassin/Arcane Trickster).")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Uncanny Dodge", "Use your reaction to halve damage from a visible attacker.")],
        6: [("Expertise", "Double your proficiency bonus in two skills.")],
        7: [("Evasion", "Take no damage on successful DEX saves, half on failure.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Archetype Feature", "Gain a new ability from your roguish archetype.")],
        10: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
    },
    "sorcerer": {
        1: [("Spellcasting", "Cast sorcerer spells from your innate magic."), ("Sorcerous Origin", "Choose a bloodline granting origin features.")],
        2: [("Font of Magic", "Convert sorcery points to spell slots and back.")],
        3: [("Metamagic", "Choose two metamagic options (e.g. Twinned Spell, Quickened Spell, Careful Spell).")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Origin Feature", "Gain a new ability from your sorcerous origin.")],
        6: [("Origin Feature", "Gain a new ability from your sorcerous origin.")],
        7: [("Metamagic", "Choose a third metamagic option.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Origin Feature", "Gain a new ability from your sorcerous origin.")],
        10: [("Metamagic", "Choose a fourth metamagic option.")],
    },
    "warlock": {
        1: [("Pact Magic", "Cast spells using Pact Magic spell slots that recharge on a short rest."), ("Otherworldly Patron", "Choose a patron granting patron features.")],
        2: [("Eldritch Invocations", "Choose eldritch invocations granting special abilities.")],
        3: [("Pact Boon", "Choose a pact boon (Pact of the Blade/Chain/Tome).")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Patron Feature", "Gain a new ability from your patron.")],
        6: [("Patron Feature", "Gain a new ability from your patron.")],
        7: [("Eldritch Invocations", "Choose additional eldritch invocations.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Patron Feature", "Gain a new ability from your patron.")],
        10: [("Eldritch Invocations", "Choose additional eldritch invocations.")],
    },
    "wizard": {
        1: [("Spellcasting", "Cast wizard spells from your spellbook."), ("Arcane Recovery", "Regain spell slots equal to half your wizard level after a short rest (once per day).")],
        2: [("Arcane Tradition", "Choose a school of magic and gain its features.")],
        3: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
        4: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        5: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
        6: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
        7: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
        8: [("Ability Score Improvement", "Increase one ability score by 2, or two scores by 1.")],
        9: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
        10: [("Tradition Feature", "Gain a new ability from your arcane tradition.")],
    },
}


# Exhaustion-straff per nivå (5e) — för _format_char_context/_apply_exhaustion_effects
_EXHAUSTION_PENALTIES = {
    1: "disadvantage on ability checks",
    2: "speed halved",
    3: "disadvantage on attack rolls and saving throws",
    4: "hit point maximum halved",
    5: "speed 0",
    6: "death",
}


def _apply_exhaustion_effects(ch: dict, level: int, effects: list) -> None:
    """5e exhaustion L4+: halvera hp.max (spara max_full), återställ vid <L4."""
    hp = _ensure_hp(ch)
    if level >= 4:
        if not hp.get("max_full"):
            hp["max_full"] = int(hp.get("max", 1) or 1)
            hp["max"] = max(1, hp["max_full"] // 2)
            hp["current"] = min(hp.get("current", 0), hp["max"])
            effects.append({"type": "exhaustion_hp_halved", "max": hp["max"]})
            logger.info("🥀 Exhaustion L%d: HP max halved → %d", level, hp["max"])
    elif hp.get("max_full"):
        hp["max"] = int(hp["max_full"])
        hp.pop("max_full", None)
        effects.append({"type": "exhaustion_recovered", "max": hp["max"]})
        logger.info("🍃 Exhaustion below L4: HP max restored → %d", hp["max"])


def _grant_skill_proficiency(ch: dict, skill_name: str) -> None:
    """Sätt proficient=true på en standard-skill (downtime-träning klar)."""
    for s in _ensure_skills(ch):
        if str(s.get("name", "")).lower() == skill_name.lower():
            s["proficient"] = True
            ch.setdefault("skills", _ensure_skills(ch))
            return


def _encumbrance_level(ch: dict, total_weight: float) -> str:
    """5e variant-encumbrance: none/light/heavy/overload mot 5×/10×/15× STR."""
    str_score = int((ch.get("abilities", {}).get("STR") or {}).get("score", 10) or 10)
    if total_weight > str_score * 15:
        return "overload"
    if total_weight > str_score * 10:
        return "heavy"
    if total_weight > str_score * 5:
        return "light"
    return "none"


def _apply_level_up_bonuses(ch: dict, effects: list) -> None:
    """Tillämpa level-up-bonusar: max HP (HD-baserat), spell slots (5e-tabell),
    hit dice total = level, klassfeatures. Delas av XP- och quest-patharna.
    (fix 2026-08-10: spell slots + hit dice uppdaterades aldrig vid level-up.)"""
    # Max HP ökar — HD-baserat (medelvärde per nivå = hd//2 + CON-mod)
    hp = _ensure_hp(ch)
    con_mod = ch.get("abilities", {}).get("CON", {}).get("mod", 0)
    _cls = str(ch.get("class", "")).lower()
    _hd = _HD_BY_CLASS.get(_cls, 8)
    hp_gain = max(1, _hd // 2 + con_mod)
    hp["max"] = hp.get("max", 1) + hp_gain
    if hp.get("max_full"):
        hp["max_full"] = hp["max_full"] + hp_gain
    hp["current"] = hp["max"]  # Full HP vid level-up
    _grant_class_features(ch, ch["level"], effects)
    effects.append({"type": "level_up", "value": ch["level"]})
    # v1.2: proficiency skalar med nivån (5e: +2→+6). Tidigare fryst på +2.
    ch["proficiency"] = 2 + (int(ch.get("level", 1) or 1) - 1) // 4
    # Spell slots max ökar per klassens 5e-tabell
    _cls_lu = str(ch.get("class", "")).lower().strip()
    slot_table = next(
        (t for key, t in _SPELL_SLOTS_BY_LEVEL.items() if key in _cls_lu),
        None,
    )
    if slot_table:
        new_max = slot_table.get(ch["level"], slot_table.get(20, 0))
        ss = ch.setdefault("spell_slots", {"current": 0, "max": 0})
        if new_max > ss.get("max", 0):
            ss["max"] = new_max
            ss["current"] = new_max  # level-up ger fulla slots
            effects.append({"type": "spell_slots_up", "value": new_max})
    # Hit Dice total = level (5e)
    hd_up = _ensure_hit_dice(ch)
    if ch["level"] > hd_up.get("total", 0):
        hd_up["total"] = ch["level"]
        hd_up["remaining"] = hd_up.get("total", ch["level"])
    logger.info("🛡️ Guardian: LEVEL UP → level %d! HP max %d (HD %d)", ch["level"], hp["max"], _hd)


def _grant_class_features(ch: dict, new_level: int, effects: list) -> None:
    """Lägg till klassfeatures vid level-up från _CLASS_FEATURES-tabellen (dedup)."""
    cls = str(ch.get("class", "")).lower().strip()
    ckey = _CLASS_ALIASES.get(cls, cls)
    feats = _CLASS_FEATURES.get(ckey, {}).get(new_level, [])
    if not feats:
        return
    features = ch.setdefault("features", [])
    if not isinstance(features, list):
        features = []
        ch["features"] = features
    existing = {str(f.get("name", "")).lower() for f in features if isinstance(f, dict)}
    added = []
    for fname, fdesc in feats:
        if fname.lower() not in existing:
            features.append({"name": fname, "level": new_level, "description": fdesc})
            existing.add(fname.lower())
            added.append(fname)
    if added:
        effects.append({"type": "features_added", "value": ", ".join(added)})
        logger.info("🛡️ Class features granted at level %d: %s", new_level, ", ".join(added))


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


def _recompute_ac_from_armor(state: dict, armor_item: dict | None) -> None:
    """v1.2 (audit-mekanik P1): AC var fryst från karaktärsskapandet —
    rustningsbyte ändrade aldrig character.ac. Räknas nu om från utrustad
    rustning: bas (ac_bonus) + DEX-mod med klass-tak (lätt=fullt, medium=+2,
    tungt=0). Klass bedöms på basvärdet: ≤11 lätt, 12–13 medium, ≥14 tungt.
    Guardian character_updates 'ac' vinner fortfarande (senare i flödet)."""
    try:
        ch = state.get("character")
        if not isinstance(ch, dict) or not isinstance(armor_item, dict):
            return
        cat = str(armor_item.get("category", "") or "").lower()
        typ = str(armor_item.get("type", "") or "").lower()
        if cat != "armor" and typ not in ("rustning", "armor"):
            return
        base = _safe_int(armor_item.get("ac_bonus"), 0)
        if base <= 0:
            return
        dex = _ability_mod(ch, "DEX")
        if base >= 14:
            dex_cap = 0
        elif base >= 12:
            dex_cap = 2
        else:
            dex_cap = 99
        new_ac = max(1, base + min(dex, dex_cap) + _safe_int(armor_item.get("magic_bonus"), 0))
        old_ac = _safe_int(ch.get("ac"), 0)
        ch["ac"] = new_ac
        ch["ac_source"] = f"equipped:{armor_item.get('name', '?')}"
        if new_ac != old_ac:
            logger.info("🛡️ AC omräknad: %d → %d (%s)", old_ac, new_ac, ch["ac_source"])
    except Exception:
        logger.exception("AC-omräkning misslyckades (tyst ignorerad)")


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
    # v1.2: price_gp överlever inlagringen (köp/sink-framtid, audit-ekonomi).
    if raw.get("price_gp") is not None:
        try:
            item["price_gp"] = float(raw["price_gp"])
        except (TypeError, ValueError):
            pass
    # Behåll befintligt id om det finns (Guardian genererar annars)
    if raw.get("id"):
        item["id"] = str(raw["id"])
    return item


def _init_turn_order(combat: dict, state: dict) -> None:
    """Bygg turn_order från enemies + allierade + spelaren. Anropas vid combat_start."""
    ch = state.get("character", {})
    player_name = ch.get("name", "Player")
    turn_order = [{"key": "player", "name": player_name, "initiative": 0, "acted": False}]
    for e in combat.get("enemies", []):
        if e.get("alive", True):
            turn_order.append({"key": f"enemy:{e.get('id', 0)}", "name": e.get("name", "?"), "initiative": 0, "acted": False})
    for a in combat.get("allies", []):
        if a.get("alive", True):
            turn_order.append({"key": f"ally-{a.get('id', 0)}", "name": a.get("name", "?"), "initiative": 0, "acted": False})
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
        logger.info("⚔️ New round %d — everyone has acted", combat["round"])
    else:
        # Stega till nästa levande combatant
        while next_idx < len(turn_order):
            entry = turn_order[next_idx]
            if entry["key"] == "player" or any(
                e.get("name", "").lower() == entry.get("name", "").lower() and e.get("alive", True)
                for e in combat.get("enemies", [])
            ) or any(
                a.get("name", "").lower() == entry.get("name", "").lower() and a.get("alive", True)
                for a in combat.get("allies", [])
            ):
                break
            next_idx += 1
        combat["current_index"] = min(next_idx, len(turn_order) - 1)
        current = turn_order[combat["current_index"]]
        combat["phase"] = "player" if current["key"] == "player" else ("enemies" if ":" in current["key"] else "allies")


def _enemy_key(e: dict, idx: int) -> str:
    """Unik bokföringsnyckel per fiende — NAMN + index. Enbart namn räcker
    inte: tre 'Archival Sentinel' (verifierat i playtest 2026-09-13) delade då
    EN flagga och runden kunde avancera efter att bara en attackerat."""
    return f"{e.get('name', '?')}#{e.get('id', idx)}"


def _sync_round_flags(combat: dict) -> dict:
    """round_acted-bokföring: {player: bool, enemies: {nyckel: bool}}.

    Tolererar äldre kampanjer utan nyckeln — byggs upp ur turordning/alive
    så en mitt-i-strid-uppdatering inte tappar vad som redan hänt.
    Bakåtkompat: äldre namn-nycklar (utan #) vägs in för alla fiender med
    det namnet (tron på att en namn-aktad = den fienden var ensam)."""
    ra = combat.get("round_acted")
    if not isinstance(ra, dict) or not isinstance(ra.get("enemies"), dict):
        ra = {"player": False, "enemies": {}}
        for t in combat.get("turn_order") or []:
            if t.get("acted", False) and t.get("key") == "player":
                ra["player"] = True
        combat["round_acted"] = ra
    legacy = {k: v for k, v in ra["enemies"].items() if "#" not in str(k)}
    for i, e in enumerate(combat.get("enemies", [])):
        key = _enemy_key(e, i)
        acted = legacy.get(str(e.get("name", "?")), not e.get("alive", True))
        ra["enemies"][key] = ra["enemies"].get(key, acted)
    # rena bort namn-nycklar som inte längre motsvarar en fiende
    known = {str(e.get("name", "?")) for e in combat.get("enemies", [])}
    for k in [k for k, v in ra["enemies"].items() if "#" not in str(k)]:
        if k not in known:
            del ra["enemies"][k]
    return ra


def _reset_round_bookkeeping(combat: dict) -> None:
    """Ny runda: spelaren får fulla handlingar igen, allt 'acted'-bokförande
    (round_acted + turn_order) töms — även vid LLM-driven combat_round."""
    for _t in combat.get("turn_order", []) or []:
        _t["acted"] = False
    combat["current_index"] = 0
    combat["player_actions"] = {"action": True, "bonus": True, "reaction": True}
    combat["round_acted"] = {"player": False, "enemies": {}}


def _auto_advance_round(combat: dict, state: dict, effects: list[dict]) -> None:
    """Server-side rund advancement (playtest 2026-09-13: 14 turer, runda 1).

    DM:en sänder i praktiken aldrig combat_round-siffror — koden räknar
    istället: har spelaren slagit/skjutit OCH varje LEVANDE fiende attackerat
    denna runda → round+1, logg rad, statusar tickas, handlingar resetas."""
    ra = combat.get("round_acted")
    if not isinstance(ra, dict) or not ra.get("player"):
        return
    alive_keys = [_enemy_key(e, i) for i, e in enumerate(combat.get("enemies", [])) if e.get("alive", True)]
    if not alive_keys or not all(ra["enemies"].get(k) for k in alive_keys):
        return
    combat["round"] = combat.get("round", 1) + 1
    new_round = combat["round"]
    combat.setdefault("log", []).append({
        "actor": "system", "name": "", "text": f"── ROUND {new_round} ──", "round": new_round,
    })
    # Statusar tickas vid varje auto-avancerad runda — samma motor som den
    # (nästan aldrig avlossade) LLM-signalen combat_round.
    from combat import _tick_all_statuses
    _tick_all_statuses(state, combat)
    _reset_round_bookkeeping(combat)
    combat["phase"] = "active"  # striden är igång — fasaden är ärlig
    effects.append({"type": "combat_round", "value": new_round})
    logger.info("⚔️ Guardian: round advanced to %d (player + all alive enemies acted)", new_round)


def _snapshot_entry(combat: dict, ch: dict, round_num: int) -> dict | None:
    """Bygg 'After the turn:'-snapshot med AUTENTISKA slut-HP: spelaren först,
    sedan fiender, sedan allierade. Taggas med den runda som just spelades
    (current_round) — även om rundan avancerade under anropet."""
    def _fmt(e: dict) -> str:
        mark = "" if e.get("alive", True) else " (dead)"
        return f"{e.get('name', '?')} {e.get('hp', '?')}/{e.get('max_hp', '?')} HP{mark}"

    def _hpf(entity: dict) -> str:
        _h = entity.get("hp") or {}
        if not isinstance(_h, dict):
            _h = {}
        return f"{entity.get('name', '?')} {_h.get('current', '?')}/{_h.get('max', '?')} HP"

    parts = [_hpf(ch)]
    parts += [_fmt(e) for e in combat.get("enemies", [])]
    parts += [_fmt(a) for a in combat.get("allies", [])]
    return {"round": round_num, "actor": "system", "name": "",
            "text": "After the turn: " + ", ".join(parts), "snapshot": True}


def _append_turn_snapshot(combat: dict, ch: dict, log: list, round_num: int) -> None:
    """Exakt EN snapshot per apply_mechanics-anrop, med korrekt (slutlig) HP.

    Samma runda + samma text → ersätt den befintliga posten in-place (ingen
    kö av identiska 'After the turn'-rader som i playtestet); annan runda
    eller annan text → append sist."""
    entry = _snapshot_entry(combat, ch, round_num)
    if entry is None:
        return
    for _i in range(len(log) - 1, -1, -1):
        _e = log[_i]
        if (isinstance(_e, dict) and _e.get("snapshot")
                and _e.get("round") == entry["round"] and _e.get("text") == entry["text"]):
            log[_i] = entry
            return
    log.append(entry)


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

    # ── Chat-first strid: kodens tärningsrullning är auktoritativ ──
    # När enemy_attacks finns och attackeraren matchar en levande fiende i
    # striden rullar KODEN utfallet (d20 + attack_bonus mot AC + skade-tärning).
    # DM-närrerade skadesiffror för samma attacker — både [SKADA:]-taggar
    # (redan applicerade av main.py) och Guardian-extraherad "damage" — får
    # INTE appliceras UTÖVER kodens skada (dubbel-skada, turn 140-buggen:
    # 4+5 tagg/extraction + 2+4 kod = 15 istället för 6).
    combat = state.get("world", {}).get("combat")
    code_rolled_attacks = bool(
        combat and combat.get("active")
        and any(
            isinstance(atk, dict)
            and str(atk.get("attacker", "")).strip()
            and any(
                str(e.get("name", "")).lower() == str(atk.get("attacker", "")).strip().lower()
                and e.get("alive", True)
                for e in combat.get("enemies", [])
            )
            for atk in mech.get("enemy_attacks", [])
        )
    )
    if code_rolled_attacks:
        # [SKADA:]-taggarna applicerades redan i main.py — återställ dem:
        # kodens rullning ERSÄTTER (adderar inte till) den narrerade skadan.
        _refund = 0
        for _t, _v in list(_skip_keys):
            if _t == "skada":
                try:
                    _refund += int(_v)
                except (TypeError, ValueError):
                    pass
        if _refund > 0:
            _hp = _ensure_hp(ch)
            _hp["current"] = min(_hp.get("max", 1), _hp.get("current", 1) + _refund)
            logger.warning(
                "🛡️ Code-rolled enemy attacks → refunding %d [SKADA:]-tag damage (code rolls are authoritative)",
                _refund,
            )
        # Tag-beloppen får inte längre dämpa kodens skade-rullar (exakt-match)
        _skip_keys = {k for k in _skip_keys if k[0] != "skada"}

    # ── Spelar-attack-dedup (2026-08-08, "svensk del 1"-incidenten) ──
    # Guardian extraherar KONSEKVENT BÅDE damage:[{target: fiende}] OCH
    # player_attacks/ally_attacks för SAMMA narrerade attack → båda grenarna
    # applicerade → dubbelskada på fienden (Kaelen 8→0 på 4 dmg).
    # Attack-vägen (player_attacks/ally_attacks med hit) är AUKTORITATIV för
    # fiende-HP; damage-arrayens entry mot samma fiende skippas.
    _attacked_enemies = {
        str(a.get("target", "")).strip().lower()
        for a in list(mech.get("player_attacks", []) or []) + list(mech.get("ally_attacks", []) or [])
        if isinstance(a, dict) and a.get("hit") and _safe_int(a.get("damage"), 0) > 0
    }

    # ── Skada ──
    from combat import damage_multiplier
    for dmg in mech.get("damage", []):
        target = dmg.get("target", "player")
        amount = max(0, _safe_int(dmg.get("amount"), 0))
        if amount <= 0:
            continue
        # 5e resistans/sårbarhet/immunitet (P2): applicera på rätt entity.
        _dtype = str(dmg.get("type", "") or "")
        if target == "player":
            _mult = damage_multiplier(_dtype, ch)
        else:
            combat = state.get("world", {}).get("combat")
            _enemy = None
            if combat and combat.get("active"):
                _enemy = next(
                    (e for e in combat.get("enemies", [])
                     if e.get("name", "").lower() == str(target).lower() and e.get("alive", True)),
                    None,
                )
            _mult = damage_multiplier(_dtype, _enemy) if _enemy is not None else 1.0
        if _mult != 1.0:
            _orig = amount
            amount = int(amount * _mult)
            effects.append({
                "type": "damage_type_mod", "target": target, "damage_type": _dtype or "unknown",
                "mult": _mult, "original": _orig, "amount": amount,
            })
            logger.info("🛡️ Damage type %s on %s → ×%s (%d → %d)", _dtype or "?", target, _mult, _orig, amount)
        if amount <= 0:
            continue
        # Spelar-attack-dedup (2026-08-08): fienden träffades redan av
        # player_attacks/ally_attacks denna tur → attack-vägen är auktoritativ,
        # skippa damage-arrayens entry (dubbelskada på fiende, "svensk del 1").
        if target != "player" and str(target).strip().lower() in _attacked_enemies:
            logger.info("🛡️ Guardian: skipping extracted damage to %s — player/ally attack already applied", target)
            continue
        # Chat-first strid: DM-närrerad spelarskada som koden redan rullar
        # (enemy_attacks) → hoppa över; kodens skada är auktoritativ.
        if code_rolled_attacks and target == "player":
            logger.info(
                "🛡️ Guardian: skipping extracted player damage %s — code-rolled enemy attacks are authoritative this turn",
                dmg.get("amount", 0),
            )
            continue
        # P0-dedup: [SKADA:]-taggen applicerade redan samma skada
        if ("skada", str(dmg.get("amount", 0))) in _skip_keys:
            continue
        if target == "player":
            hp = _ensure_hp(ch)
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
                    "name": ch.get("name", "Player"),
                    "text": f"hits {enemy['name']} — {amount} damage ({dmg.get('type', 'unknown')})",
                })
                effects.append({"type": "combat_dmg", "value": enemy["name"], "amount": amount})
                logger.info("⚔️ Guardian: %s takes %d damage → %d/%d", enemy["name"], amount, enemy["hp"], enemy.get("max_hp", 0))
                if enemy["hp"] <= 0:
                    enemy["alive"] = False
                    effects.append({"type": "enemy_död", "value": enemy["name"]})
                    logger.info("💀 %s has fallen in battle", enemy["name"])
            else:
                _add_npc_note(state, target, f"Took {amount} damage ({dmg.get('type', 'unknown')})")

    # ── Läkning ──
    for heal in mech.get("healing", []):
        target = heal.get("target", "player")
        amount = max(0, _safe_int(heal.get("amount"), 0))
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
            logger.info("🛡️ Guardian: potion-heal → roll_grant 2d4+2 (instead of flat %d)", amount)
            continue
        if amount <= 0:
            continue
        # P0-dedup: [HELA:]-taggen applicerade redan samma läkning
        if ("hela", str(heal.get("amount", 0))) in _skip_keys:
            continue
        if target == "player":
            hp = _ensure_hp(ch)
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
                "text": "All enemies defeated — the battle is over",
            })
            effects.append({"type": "combat_end", "value": "all defeated"})
            logger.info("🏁 Combat over — all enemies defeated")

    # ── XP ──
    xp_gain = max(0, _safe_int(mech.get("xp"), 0))
    if xp_gain > 0:
        # P0-dedup: [XP:]-taggen applicerade redan samma XP
        if ("xp", str(mech.get("xp", 0))) not in _skip_keys:
            xp = _ensure_xp(ch)
            xp["current"] = _safe_int(xp.get("current"), 0) + xp_gain
            effects.append({"type": "xp", "value": xp_gain})
            logger.info("🛡️ Guardian: +%d XP → %d", xp_gain, xp["current"])

    # Level-up check (audit 2026-09-06 §5): körs ALLTID — även när xp_gain == 0
    # (XP kan ha kommit via [XP:]-taggen eller quest-reward-vägen, eller så sitter
    # karaktären redan över tröskeln). WHILE-loop → multi-level per tur möjligt.
    _check_level_ups(ch, effects)

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
                _recompute_ac_from_armor(state, existing)  # v1.2: AC följer rustning
            logger.info("🛡️ Guardian dedup: '%s' → qty=%d", name, existing["qty"])
        else:
            new_item = dict(norm)
            new_item.setdefault("id", f"guardian-{len(inv)}")
            inv.append(new_item)
            if norm.get("equipped"):
                _unequip_same_type(inv, norm["type"], name)
                _recompute_ac_from_armor(state, new_item)  # v1.2: AC följer rustning
            logger.info("🛡️ Guardian: added '%s'", name)
        current_weight += added_weight
        effects.append({"type": "föremål", "value": name, "qty": qty})

    # ── Besvärjelser (v28): spells_add — karaktären lär sig en besvärjelse ──
    for sp in mech.get("spells_add", []):
        if not isinstance(sp, dict) or not sp.get("name"):
            continue
        sname = str(sp.get("name", "")).strip()[:80]
        if not sname:
            continue
        spells = ch.setdefault("spells", [])
        if any((s.get("name") or "").lower() == sname.lower() for s in spells):
            continue  # redan känd — dedup
        spells.append({
            "name": sname,
            "level": _safe_int(sp.get("level"), 0),
            "school": str(sp.get("school", "")).strip()[:40] or "Okänd",
            "casting_time": str(sp.get("casting_time", "")).strip()[:40] or "",
            "damage_dice": str(sp.get("damage_dice", "")).strip()[:40] or None,
            "description": str(sp.get("description", "")).strip()[:300] or "",
        })
        effects.append({"type": "spell_add", "value": sname, "level": _safe_int(sp.get("level"), 0)})
        logger.info("✨ Guardian: spell added '%s' (lvl %s)", sname, sp.get("level", 0))

    for item in mech.get("items_remove", []):
        # Robust mot både dict- och sträng-form (samma klass av bugg som death)
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            qty = max(1, _safe_int(item.get("qty"), 1))
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
        amount = _safe_int(c.get("amount"), 0)
        if denom in cur:
            # P0-dedup: [GULD:]-taggen applicerade redan samma ändring
            if ("guld", str(c.get("amount", 0))) in _skip_keys:
                continue
            # v1.2: saldakontroll i cp — vägra istället för max(0)-clamp som
            # förintade mynt tyst (−10 gp med 5 gp gav 0 gp, 5 gp borta).
            _CP = {"pp": 1000, "gp": 100, "sp": 10, "cp": 1}
            if amount < 0:
                _have_cp = sum(int(cur.get(k, 0) or 0) * _CP[k] for k in _CP)
                if abs(amount) * _CP[denom] > _have_cp:
                    effects.append({"type": "guld_fail", "value": abs(amount), "denom": denom})
                    logger.warning("🛡️ Guardian: vägrar −%d %s, saldot räcker inte (%d cp)",
                                   abs(amount), denom, _have_cp)
                    continue
            cur[denom] = int(cur.get(denom, 0) or 0) + amount
            effects.append({"type": "guld", "value": amount, "denom": denom})
            logger.info("🛡️ Guardian: %+d %s → %d", amount, denom, cur[denom])

    # ── Encumbrance (5e, P2) — variantregel: 5×/10×/15× STR ──
    _inv_w = sum(float(it.get("weight", 0) or 0) * int(it.get("qty", 1) or 1) for it in state.get("inventory", []))
    _coin_total = sum(int(cur.get(k, 0) or 0) for k in ("pp", "gp", "sp", "cp"))
    _total_w = _inv_w + _coin_total / 50.0  # 5e: 50 mynt = 1 lb
    _enc_level = _encumbrance_level(ch, _total_w)
    _old_enc = ch.setdefault("_encumb", "none")
    if _enc_level != _old_enc:
        ch["_encumb"] = _enc_level
        effects.append({"type": "encumbrance", "level": _enc_level, "weight": round(_total_w, 1)})
        if _enc_level != "none":
            logger.info("🛡️ Encumbrance: %s (%.1f lb)", _enc_level, _total_w)

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
                "xp_reward": _safe_int(q.get("xp_reward"), 100),  # Default 100 XP
                "gold_reward": _safe_int(q.get("gold_reward"), 0),
                "status": "aktiv",
                "created_turn": state.get("meta", {}).get("turn_count", 0),
            })
            effects.append({"type": "quest", "value": name})
            logger.info("🛡️ Guardian: new quest '%s' (ID: %s)", name, quest_id[:8])

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
            xp_r = _safe_int(q.get("xp_reward"), 0)
            llm_xp = _safe_int(mech.get("xp"), 0)
            if xp_r > 0 and ("xp", str(xp_r)) not in _skip_keys and llm_xp != xp_r:
                xp = _ensure_xp(ch)
                xp["current"] = _safe_int(xp.get("current"), 0) + xp_r
                effects.append({"type": "xp", "value": xp_r, "source": "quest"})
                logger.info("🛡️ Guardian: +%d XP (quest-reward '%s') → %d", xp_r, q["name"], xp["current"])
                # Level-up check: WHILE-motor (multi-level), delad med xp-sektionen
                _check_level_ups(ch, effects)

            # Guld-reward
            gold_r = int(q.get("gold_reward", 0) or 0)
            # v1.2 belt-braces: hoppa över om [GULD:]-taggen/QUEST-path redan betalat
            if gold_r > 0 and ("guld", str(gold_r)) not in _skip_keys:
                cur = state.setdefault("currency", {"pp": 0, "gp": 0, "sp": 0, "cp": 0})
                cur["gp"] = cur.get("gp", 0) + gold_r
                effects.append({"type": "guld", "value": gold_r, "denom": "gp", "source": "quest"})
                logger.info("🛡️ Guardian: +%d gp (quest-reward '%s')", gold_r, q["name"])
        else:
            logger.warning("🛡️ Guardian: quests_completed matched no active quest: '%s'", name)

    for name in mech.get("quests_failed", []):
        if not isinstance(name, str) or not name.strip():
            continue
        q = _find_quest(name, require_active=True)
        if q:
            q["status"] = "misslyckad"
            effects.append({"type": "quest_misslyckad", "value": q["name"]})
            logger.info("🛡️ Guardian: quest failed '%s'", q["name"])
        else:
            logger.warning("🛡️ Guardian: quests_failed matched no active quest: '%s'", name)

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
                "near": False,
                "color": _colors[h % len(_colors)],
                "icon": _icons[h % len(_icons)],
                "notes": "",
                "alive": True,
            })
            effects.append({"type": "npc_new", "value": name, "role": npc.get("role", "Okänd"), "relation": relation})
            logger.info("🛡️ Guardian: new NPC '%s' (%s)", name, relation)

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

    # ── Närvaro: vilka NPCs befinner sig i spelarens direkta närhet just nu ──
    near_names = [str(n).strip().lower() for n in mech.get("npcs_near", []) if isinstance(n, str) and n.strip()]
    for npc in npcs:
        was_near = bool(npc.get("near", False))
        is_near = npc.get("name", "").lower() in near_names
        if was_near != is_near:
            npc["near"] = is_near
            effects.append({"type": "npc_near", "value": f"{npc.get('name', '?')} → {'nära' if is_near else 'lämnade närheten'}"})
            logger.info("🛡️ Guardian: NPC '%s' presence → %s", npc.get("name"), "near" if is_near else "left")

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
            logger.info("🛡️ Guardian: new location '%s' (%s)", name, loc_obj["terrain"])

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
            logger.info("🛡️ Guardian: position verified '%s' (unchanged)", new_pos)
        else:
            if old_pos and old_pos != new_pos:
                world.setdefault("travel_log", []).append(
                    {"from": old_pos, "to": new_pos, "day": world.get("day", 1)}
                )
                logger.info("🛡️ Guardian: travel %s → %s (day %d)", old_pos, new_pos, world.get("day", 1))
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
        hours = _safe_int(tp.get("hours"), 0)
        desc = tp.get("description", "")
        if hours > 0:
            world["time"] = desc or world.get("time", "")
            effects.append({"type": "tid", "value": desc or f"{hours}h"})
            logger.info("🛡️ Guardian: %dh passes — %s", hours, desc)

    # ── Vila (5e: Hit Dice) ──
    rest = mech.get("rest")
    # Fallback (fix 2026-08-10): Guardian LLM:n satte time_passed/new_day men
    # INTE rest — lång vila gick aldrig igenom mekaniskt, spell slots återställdes
    # inte (testadventure turn 64-65). Om 8h+ passerat utan explicit rest,
    # tolka det som lång vila så att HP/slots/hit dice faktiskt återställs.
    if not (rest and isinstance(rest, dict)):
        tp_fb = mech.get("time_passed")
        if isinstance(tp_fb, dict):
            try:
                tp_hours = int(tp_fb.get("hours", 0) or 0)
            except (TypeError, ValueError):
                tp_hours = 0
            tp_desc = str(tp_fb.get("description", "") or "").lower()
            rest_hint = any(k in tp_desc for k in ("long rest", "lång vila", "overnight", "övernattning", "sover", "sleep"))
            if tp_hours >= 8 or rest_hint:
                rest = {"kind": "long"}
                logger.info("🛡️ Guardian: LONG REST fallback (time_passed %sh: %s) → mekanisk återställning",
                            tp_hours, tp_fb.get("description", ""))
    if rest and isinstance(rest, dict):
        kind = rest.get("kind", "short")
        hp = _ensure_hp(ch)
        hd = _ensure_hit_dice(ch)
        if kind == "long":
            hp["current"] = hp.get("max", 1)
            hp["temp"] = 0
            ss = ch.setdefault("spell_slots", {"current": 0, "max": 0})
            ss["current"] = ss.get("max", 0)
            # v1.2 5e: lång vila återställer HALVA hit dice (min 1), ej alla.
            _hd_total = int(hd.get("total", 1) or 1)
            hd["remaining"] = min(_hd_total, int(hd.get("remaining", 0) or 0) + max(1, _hd_total // 2))
            # Exhaustion (5e, P2): lång vila sänker 1 nivå
            _exh = int(ch.get("exhaustion", 0) or 0)
            if _exh > 0:
                ch["exhaustion"] = _exh - 1
                _apply_exhaustion_effects(ch, _exh - 1, effects)
                effects.append({"type": "exhaustion", "level": _exh - 1, "source": "long_rest"})
                logger.info("🍃 LONG REST → exhaustion %d → %d", _exh, _exh - 1)
            effects.append({"type": "hela", "value": hp.get("current", 0)})
            logger.info("🛡️ Guardian: LONG REST → full HP + spell slots + hit dice restored")
        else:
            # Kort vila (5e): spendera 1 Hit Die → 1dX + CON-mod
            if hd.get("remaining", 0) > 0:
                die = hd.get("dice", "1d8")
                sides = int(re.sub(r"[^0-9]", "", die) or 8)
                con_mod = _ability_mod(ch, "CON")
                # v1.2: cryptographically secure — samma källa som övriga kast.
                rolled = secrets.randbelow(sides) + 1
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
            logger.info("🛡️ Guardian day summary Day %d: %s", prev_day, ds.get("title", ""))

        effects.append({"type": "ny_dag", "value": f"Dag {world['day']}: {desc}"})
        logger.info("🛡️ Guardian: NEW DAY %d — %s", world["day"], desc)

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
                    "player_cover": None,
                    "started_turn": state.get("meta", {}).get("turn_count", 0),
                    "ended_turn": None,
                }
                combat = world["combat"]
                _init_turn_order(combat, state)
                # Ärlig fas: striden är igång så fort fienderna finns —
                # 'awaiting_initiative' låste UI:t i playtestet (2026-09-13).
                combat["phase"] = "active"
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
            # Conditions tick (5e, 2026-08-08): status-skada + status-utgång vid
            # rundstart — samma motor som advance_turn (test-only tidigare).
            from combat import _tick_all_statuses
            _tick_all_statuses(state, combat)
            effects.append({"type": "combat_round", "value": new_round})
            logger.info("⚔️ Guardian: new round %d (statuses ticked)", new_round)

    if combat and combat.get("active"):
        for ent in mech.get("initiative_entries", []) or []:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            value = _safe_int(ent.get("value"), 0)
            initiative = combat.setdefault("initiative", [])
            # Ersätt befintlig entry med samma namn (spelare eller fiende),
            # behåll rätt KEY — v1.2-fix: spelarnamn fick tidigare 'enemy:0'.
            def _pl_name(ch):
                return str((state.get("character") or {}).get("name", "") or "").lower()
            _is_player = name.lower() == _pl_name(ch) or name.lower() in ("player", "spelaren")
            _old = next((e for e in initiative if e.get("name", "").lower() == name.lower()), None)
            if _is_player:
                new_key = "player"
            elif _old is not None:
                new_key = _old.get("key")  # bevara befintlig identitet
            else:
                eid = next((i for i, e in enumerate(combat.get("enemies", [])) if e.get("name", "").lower() == name.lower()), None)
                new_key = f"enemy:{eid}" if eid is not None else f"npc:{name.lower()[:20]}"
            initiative[:] = [e for e in initiative if e.get("name", "").lower() != name.lower()]
            initiative.append({"key": new_key, "name": name, "value": value})
            effects.append({"type": "initiativ", "value": f"{name}: {value}"})
            logger.info("🎲 Guardian initiative: %s → %d", name, value)

    ce = mech.get("combat_end")
    if ce and combat and combat.get("active"):
        reason = (ce.get("reason") or "striden avslutades") if isinstance(ce, dict) else str(ce)
        combat["active"] = False
        combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
        combat["player_cover"] = None  # cover upphör när striden slutar
        # Strids-slut-städ (playtest 2026-09-13: Rust-Husk 'defeated' vid
        # 10/22 HP, alive=true — narrativt dött men mekaniskt levande).
        # mech['defeated'] (explicit lista) vinner; annars fiender vars
        # senaste egen loggpost i denna strid är en 'falls!'-rad nollas.
        _defeated = {str(d).strip().lower() for d in (mech.get("defeated") or []) if str(d).strip()}
        if isinstance(ce, dict):
            _defeated |= {str(d).strip().lower() for d in (ce.get("defeated") or []) if str(d).strip()}
        _standing = 0
        for e in combat.get("enemies", []):
            if not e.get("alive", True):
                continue
            ename = str(e.get("name", "?"))
            _last_own = None
            for _ent in combat.get("log", []):
                _txt = str(_ent.get("text", ""))
                if str(_ent.get("name", "")).lower() == ename.lower() or f"{ename.lower()} falls" in _txt.lower():
                    _last_own = _txt.lower()
            if ename.lower() in _defeated or (_last_own and "falls" in _last_own):
                e["hp"] = 0
                e["alive"] = False
                logger.info("💀 Guardian combat_end: %s nollad vid stridsslut (narrativt död)", ename)
            else:
                _standing += 1
        if _standing:
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "system", "name": "",
                "text": f"combat ended — {_standing} enemies still standing",
            })
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "system", "name": "", "text": f"Striden avslutades — {reason}",
        })
        effects.append({"type": "combat_end", "value": reason})
        logger.info("🏁 Guardian combat_end: %s", reason)

    # ── Chat-first combat: player_attacks, enemy_attacks, combat_events ──
    combat = state.get("world", {}).get("combat")
    if combat and combat.get("active"):
        combat_log = combat.setdefault("log", [])
        current_round = combat.get("round", 1)
        _ra = _sync_round_flags(combat)  # rund-bokföring (tolerar äldre state)
        # Ärlig fas: '[STRID:]'-öppnade strider fastnar på 'awaiting_initiative'
        # i chat-first-flödet (ingen initiativsväg skriver om den) — så fort
        # någon faktiskt slårss är striden aktiv.
        if combat.get("phase") == "awaiting_initiative" and (
            mech.get("player_attacks") or mech.get("enemy_attacks")
            or mech.get("ally_attacks") or mech.get("ally_damage")
        ):
            combat["phase"] = "active"

        # Spelarens attacker → minska fiende-HP
        for atk in mech.get("player_attacks", []):
            target_name = str(atk.get("target", "")).strip()
            if not target_name:
                continue
            enemy = next((e for e in combat.get("enemies", []) if e.get("name", "").lower() == target_name.lower() and e.get("alive", True)), None)
            if not enemy:
                continue
            _ra["player"] = True  # spelaren har agerat denna runda (även miss)
            if atk.get("hit"):
                # v1.2 "The Honest Dice": motorrullad spelarskada — vapnets
                # damage_dice ur inventory, ej DM-narrerat heltal (kontrakt v28).
                dmg = 0
                roll_note = ""
                try:
                    from combat import roll_dice as _roll_dice_pl
                    wname = str(atk.get("weapon", "") or "").strip().lower()
                    weapons = [it for it in state.get("inventory", [])
                               if (it.get("damage_dice") or "").strip()
                               and (it.get("equipped") or it.get("usage") == "wielded")]
                    weapon = next((w for w in weapons if wname and wname in str(w.get("name", "")).lower()),
                                  weapons[0] if weapons else None)
                    if weapon:
                        notation = str(weapon["damage_dice"]).strip()
                        mb = _safe_int(weapon.get("magic_bonus"), 0)
                        if mb:
                            notation = notation + ("+%d" % mb if mb > 0 else "%d" % mb)
                        dmg, _rolls = _roll_dice_pl(notation)
                        if atk.get("crit"):
                            dmg2, _rolls2 = _roll_dice_pl(notation)
                            dmg += dmg2
                        roll_note = f" (🎲 {notation}={'×2 ' if atk.get('crit') else ''}{dmg})"
                except Exception:
                    roll_note = ""
                if dmg <= 0:
                    # inget vapen med dice (ostadie/natural) → LLM-värde som förut
                    dmg = max(0, _safe_int(atk.get("damage"), 0))
                if dmg > 0:
                    enemy["hp"] = max(0, enemy.get("hp", 0) - dmg)
                    crit_str = " 💥 KRITISK!" if atk.get("crit") else ""
                    combat_log.append({"round": current_round, "actor": "player", "name": ch.get("name", "Player"), "text": f"hits {enemy['name']} — {dmg} damage ({atk.get('damage_type', 'unknown')}){crit_str}{roll_note} → **{enemy['name']} {enemy['hp']}/{enemy.get('max_hp', '?')} HP**"})
                    effects.append({"type": "combat_dmg", "value": enemy["name"], "amount": dmg})
                    logger.info("⚔️ Player attack: %s → %s, %d damage → HP %d/%d", ch.get("name"), enemy["name"], dmg, enemy["hp"], enemy.get("max_hp", 0))
                    if enemy["hp"] <= 0:
                        enemy["alive"] = False
                        combat_log.append({"round": current_round, "actor": "system", "name": "", "text": f"{enemy['name']} falls!"})
                        effects.append({"type": "enemy_död", "value": enemy["name"]})
                        logger.info("💀 %s has fallen", enemy["name"])
            else:
                combat_log.append({"round": current_round, "actor": "player", "name": ch.get("name", "Player"), "text": f"misses {enemy['name']}"})

        # ── status_apply (v1.2): villkormotorn LEVANDE — tidigare konsumera-
        # des aldrig (DM-prompten lovade grapple→restrained som aldrig hände).
        for st in mech.get("status_apply", []):
            if not isinstance(st, dict):
                continue
            sname = str(st.get("name", "")).strip().lower()
            if not sname:
                continue
            stgt = str(st.get("target", "player")).strip().lower()
            sdu = max(1, _safe_int(st.get("duration"), 2))
            try:
                from combat import add_status as _add_st
                entity = None
                if stgt in ("player", "spelaren", ch.get("name", "").lower()):
                    entity = ch
                else:
                    entity = next((e for e in combat.get("enemies", [])
                                  if e.get("name", "").lower() == stgt and e.get("alive", True)), None) \
                        or next((a for a in combat.get("allies", [])
                                 if a.get("name", "").lower() == stgt and a.get("alive", True)), None)
                if entity is None:
                    continue
                _add_st(entity, sname, sdu)
                combat_log.append({"round": current_round, "actor": "system", "name": "",
                                   "text": f"{entity.get('name', '?')} drabbas av {sname} ({sdu} runder)"})
                effects.append({"type": "status", "value": f"{entity.get('name', '?')}: {sname}", "amount": sdu})
                logger.info("⚔️ Status: %s → %s (%d rundor)", entity.get("name"), sname, sdu)
            except Exception:
                logger.exception("status_apply misslyckades (tyst ignorerad)")

        # Allierades attacker → minska fiende-HP (samma mönster som spelarens;
        # allierade = vänliga NPC:er som DM lagt till via [ALLIERAD:]-taggen)
        for atk in mech.get("ally_attacks", []):
            ally_name = str(atk.get("ally", "")).strip()
            target_name = str(atk.get("target", "")).strip()
            if not ally_name or not target_name:
                continue
            enemy = next((e for e in combat.get("enemies", []) if e.get("name", "").lower() == target_name.lower() and e.get("alive", True)), None)
            if not enemy:
                continue
            # Allierade räknas som spelarsidan i rund-bokföringen (samma grind)
            _ra["player"] = True
            if atk.get("hit"):
                dmg = max(0, _safe_int(atk.get("damage"), 0))
                if dmg > 0:
                    enemy["hp"] = max(0, enemy.get("hp", 0) - dmg)
                    crit_str = " 💥 KRITISK!" if atk.get("crit") else ""
                    roll_str = f" (🎲 d20={atk.get('roll', '?')})" if atk.get("roll") else ""
                    combat_log.append({"round": current_round, "actor": "ally", "name": ally_name, "text": f"hits {enemy['name']} — {dmg} damage ({atk.get('damage_type', 'unknown')}){crit_str}{roll_str} → **{enemy['name']} {enemy['hp']}/{enemy.get('max_hp', '?')} HP**"})
                    effects.append({"type": "combat_dmg", "value": enemy["name"], "amount": dmg})
                    logger.info("🤝 Ally attack: %s → %s, %d damage → HP %d/%d", ally_name, enemy["name"], dmg, enemy["hp"], enemy.get("max_hp", 0))
                    if enemy["hp"] <= 0:
                        enemy["alive"] = False
                        combat_log.append({"round": current_round, "actor": "system", "name": "", "text": f"{enemy['name']} falls!"})
                        effects.append({"type": "enemy_död", "value": enemy["name"]})
                        logger.info("💀 %s has fallen", enemy["name"])
            else:
                roll_str = f" (🎲 d20={atk.get('roll', '?')})" if atk.get("roll") else ""
                combat_log.append({"round": current_round, "actor": "ally", "name": ally_name, "text": f"misses {enemy['name']}{roll_str}"})

        # Allierade tar skada → minska ally-HP; dödlig skada → alive=false
        for atk in mech.get("ally_damage", []):
            ally_name = str(atk.get("ally", "")).strip()
            if not ally_name:
                continue
            ally = next((a for a in combat.get("allies", []) if a.get("name", "").lower() == ally_name.lower() and a.get("alive", True)), None)
            if not ally:
                continue
            amount = max(0, _safe_int(atk.get("amount"), 0))
            if amount <= 0:
                continue
            ally["hp"] = max(0, ally.get("hp", 0) - amount)
            attacker = str(atk.get("attacker", "")).strip() or "the enemy"
            combat_log.append({"round": current_round, "actor": "enemy", "name": attacker, "text": f"hits {ally['name']} — {amount} damage ({atk.get('damage_type', 'unknown')}) → **{ally['name']} {ally['hp']}/{ally.get('max_hp', '?')} HP**"})
            effects.append({"type": "ally_dmg", "value": ally["name"], "amount": amount})
            logger.info("🤝 Ally damage: %s takes %d damage → HP %d/%d", ally["name"], amount, ally["hp"], ally.get("max_hp", 0))
            if ally["hp"] <= 0:
                ally["alive"] = False
                combat_log.append({"round": current_round, "actor": "system", "name": "", "text": f"{ally['name']} falls!"})
                effects.append({"type": "ally_död", "value": ally["name"]})
                logger.info("💀 %s has fallen", ally["name"])

        # Fiendernas attacker → KODEN rullar tärningarna (transparens — inte DM-fusk)
        # Guardian extraherar bara attackeraren; d20 + attack_bonus mot spelarens
        # AC och skade-tärningarna rullas här, precis som spelarens egna kast.
        hp = _ensure_hp(ch)
        player_ac = _safe_int(ch.get("ac"), 10)
        for atk in mech.get("enemy_attacks", []):
            attacker_name = str(atk.get("attacker", "")).strip()
            if not attacker_name:
                continue
            # Dublettnamn (3x "Sentinel"): varje attackerande namn roteras till
            # nästa LEVANDE fiende med det namnet som ännu inte agerat — annars
            # markeras samma fiende N gånger och rundan låser sig ( regression
            # 2026-09-13: tre Archival Sentinels, round_acted fastnade på 1/3).
            _alive = [e for e in combat.get("enemies", [])
                      if e.get("name", "").lower() == attacker_name.lower() and e.get("alive", True)]
            enemy = next(
                (e for e in _alive
                 if not _ra["enemies"].get(_enemy_key(e, combat["enemies"].index(e)))),
                _alive[0] if _alive else None,
            )
            # Fiendens stats från combat (fallback: attackeraren finns inte i listan → använd DM:s angivna hit/damage om de finns)
            if enemy is not None:
                _i = next((i for i, e in enumerate(combat.get("enemies", [])) if e is enemy), 0)
                _ra["enemies"][_enemy_key(enemy, _i)] = True  # JUSTE denna fiende har agerat (träff/miss oavsett)
                from combat import roll_d20, roll_dice as _roll_dice, has_disadvantage, damage_multiplier

                # Cover (5e, P2): combat.player_cover → AC-bonus mot fiendeträffar
                _player_cover = combat.get("player_cover")
                cover_bonus = 2 if _player_cover == "half" else 5 if _player_cover == "three_quarters" else 0
                if _player_cover == "full":
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": "cannot hit you — behind full cover"})
                    effects.append({"type": "enemy_miss", "value": attacker_name, "roll": 0, "d20": 0, "bonus": 0, "reason": "full_cover"})
                    continue

                d20 = roll_d20()
                # Disadvantage (5e, 2026-08-08): status med attack_disadvantage
                # (blind/prone/frighten/stun/restrain) → 2d20, ta SÄMST.
                if has_disadvantage(enemy):
                    d20 = min(d20, roll_d20())
                attack_bonus = _safe_int(enemy.get("attack_bonus"), 3)
                total = d20 + attack_bonus
                crit = d20 == 20
                fumble = d20 == 1
                if fumble:
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": "misses you (natural 1!)"})
                    effects.append({"type": "enemy_miss", "value": attacker_name, "roll": total, "d20": d20, "bonus": attack_bonus})
                    continue
                if total < player_ac + cover_bonus and not crit:
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"misses you (🎲 d20={d20}+{attack_bonus}={total} vs AC {player_ac}{'+' + str(cover_bonus) if cover_bonus else ''})"})
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
                # 5e resistans/sårbarhet (P2): spelarens damage-type-modifierare
                dmg_type = str(atk.get("damage_type") or enemy.get("damage_type") or "")
                if dmg_type:
                    _dmult = damage_multiplier(dmg_type, ch)
                    if _dmult != 1.0:
                        dmg = int(dmg * _dmult)
                        effects.append({"type": "damage_type_mod", "target": "player", "damage_type": dmg_type, "mult": _dmult, "amount": dmg})
                        logger.info("🛡️ Player %s-resistance vs %s → ×%s → %d dmg", dmg_type, attacker_name, _dmult, dmg)
                if dmg <= 0:
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"hits you — but you are immune to {dmg_type} damage"})
                    effects.append({"type": "enemy_hit", "value": attacker_name, "damage": 0, "crit": crit, "roll": total, "d20": d20, "bonus": attack_bonus, "immune": dmg_type})
                    continue
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
                combat_log.append({
                    "round": current_round, "actor": "enemy", "name": attacker_name,
                    "text": f"hits you — {dmg} damage ({dmg_type or 'unknown'}){crit_str} (🎲 d20={d20}+{attack_bonus}={total} · {dmg_notation}: [{', '.join(str(x) for x in rolls)}]={dmg}) → **{ch.get('name', 'Player')} {hp['current']}/{hp['max']} HP**",
                })
                effects.append({
                    "type": "enemy_hit", "value": attacker_name, "damage": dmg, "crit": crit,
                    "roll": total, "d20": d20, "bonus": attack_bonus,
                    "damage_dice": dmg_notation, "damage_rolls": rolls,
                })
                logger.info("⚔️ Enemy attack: %s → the player, %d damage (d20=%d) → HP %d/%d", attacker_name, dmg, d20, hp["current"], hp["max"])
            else:
                # Fienden finns inte i combat-listan (t.ex. narrativ attack utanför strid) —
                # fallback till DM:s angivna utfall (gamla beteendet)
                if atk.get("hit"):
                    dmg = max(0, _safe_int(atk.get("damage"), 0))
                    if dmg > 0:
                        if ("skada", str(dmg)) in _skip_keys:
                            continue
                        temp = hp.get("temp", 0)
                        if temp > 0:
                            absorbed = min(temp, dmg)
                            hp["temp"] = temp - absorbed
                            dmg -= absorbed
                        hp["current"] = max(0, hp.get("current", 1) - dmg)
                        roll_str = f" (🎲 d20={atk.get('roll', '?')})" if atk.get("roll") else ""
                        combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"hits you — {dmg} damage ({atk.get('damage_type', 'unknown')}){roll_str} → **{ch.get('name', 'Player')} {hp['current']}/{hp['max']} HP**"})
                        effects.append({"type": "skada", "value": dmg})
                        logger.info("⚔️ Enemy attack (narrative): %s → the player, %d damage → HP %d/%d", attacker_name, dmg, hp["current"], hp["max"])
                else:
                    roll_str = f" (🎲 d20={atk.get('roll', '?')})" if atk.get("roll") else ""
                    combat_log.append({"round": current_round, "actor": "enemy", "name": attacker_name, "text": f"misses you{roll_str}"})

        # Combat events → logga
        for event in mech.get("combat_events", []):
            event_str = str(event).strip()
            if event_str:
                combat_log.append({"round": current_round, "actor": "system", "name": "", "text": event_str})

        # ── Turordning (chat-first): server-driven rund-avancering ──
        # Playtest 2026-09-13 (051130a1a73d): 14 turer, runda 1 — DM sänder
        # aldrig combat_round-siffror och turn_order är tom i chat-first-flödet
        # (combat.start_combat lämnar den []). Koden räknar nu rundorna själva:
        # round_acted bokförs i attacker-looparna ovan; när spelaren OCH alla
        # levande fiender agerat → ny runda (banner + status-tick + reset).
        if mech.get("combat_round"):
            # LLM-signalen är auktoritativ för HöGRE rundenummer (redan
            # tillämpad uppe i cr-handläggaren) — starta runda + bokföring
            # freskt så inte auto-avanceringen dubbelräknar.
            _reset_round_bookkeeping(combat)
        else:
            _auto_advance_round(combat, state, effects)

        # Auto-avsluta strid om alla fiender döda
        if all(not e.get("alive", True) for e in combat.get("enemies", [])) and combat.get("enemies"):
            combat["active"] = False
            combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
            combat_log.append({"round": current_round, "actor": "system", "name": "", "text": "All enemies defeated — the battle is over"})
            effects.append({"type": "combat_end", "value": "all defeated"})
            logger.info("🏁 Combat over — all enemies defeated")
        else:
            # State-snapshot EFTER alla handlers — exakt EN per anrop med
            # korrekt HP (den gamla mitten-i-strömmen-versionen fastnade på
            # '22/22' efter -6-6 och dubblerades 6x per runda).
            _append_turn_snapshot(combat, ch, combat_log, current_round)

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
        logger.info("🛡️ Guardian logbook: %s", logbook[:80])

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

    # ── Spell slots (5e, 2026-08-08) — koden förbrukar slots ──
    # Guardian anger {name, level} när spelaren kastar en besvärjelse på nivå 1+.
    # Cantrips (level 0) är gratis. Insufficient → narration vinner, blockeras.
    for cast in mech.get("spell_slots_spend", []):
        if not isinstance(cast, dict):
            continue
        name = str(cast.get("name", "")).strip() or "?"
        try:
            level = int(cast.get("level", 0) or 0)
        except (TypeError, ValueError):
            level = 0
        if level <= 0:
            continue
        slots = ch.setdefault("spell_slots", {"current": 0, "max": 0})
        if isinstance(slots, dict) and slots.get("current", 0) >= level:
            slots["current"] = int(slots.get("current", 0)) - level
            effects.append({"type": "spell_slots_spend", "name": name, "level": level, "remaining": slots["current"]})
            logger.info("🪄 Spell slot spent: %s (lvl %d) → %d/%d remaining", name, level, slots["current"], slots.get("max", 0))
        else:
            effects.append({"type": "spell_slots_blocked", "name": name, "level": level})
            logger.info("⛔ Spell slots insufficient for %s (lvl %d) — narration only", name, level)

    # ── Inspiration (5e meta-currency, 2026-08-08) ──
    if mech.get("inspiration_gain"):
        ch["inspiration"] = True
        effects.append({"type": "inspiration_gain"})
        logger.info("✨ Inspiration awarded to %s", ch.get("name", "player"))
    if mech.get("inspiration_spend"):
        if ch.get("inspiration"):
            ch["inspiration"] = False
            effects.append({"type": "inspiration_spend"})
            logger.info("✨ Inspiration spent — next roll may claim advantage")
        else:
            logger.info("⛔ Inspiration spend ignored — character has no inspiration")

    # ── Exhaustion (5e, P2) ──
    _exh_change = int(mech.get("exhaustion_change", 0) or 0)
    if _exh_change:
        old_exh = int(ch.get("exhaustion", 0) or 0)
        new_exh = max(0, min(6, old_exh + _exh_change))
        if new_exh != old_exh:
            ch["exhaustion"] = new_exh
            effects.append({"type": "exhaustion", "level": new_exh})
            logger.info("🥀 Exhaustion %d → %d (%+d)", old_exh, new_exh, _exh_change)
            _apply_exhaustion_effects(ch, new_exh, effects)
            if new_exh >= 6:
                hp = _ensure_hp(ch)
                hp["current"] = 0
                effects.append({"type": "death", "value": "exhaustion"})
                logger.warning("💀 Character died of exhaustion (level 6)")

    # ── Cover (5e, P2) — bara spelaren (fiendens cover är narrativ/prompt-styrt) ──
    _cs = mech.get("cover_set")
    if _cs is not None and isinstance(_cs, dict):
        _cov = _cs.get("cover")
        _target = str(_cs.get("target", "player") or "player")
        if _target == "player":
            combat_state = state.get("world", {}).get("combat")
            if combat_state is not None:
                if _cov in ("half", "three_quarters", "full", None):
                    combat_state["player_cover"] = _cov
                    effects.append({"type": "cover_set", "cover": _cov})
                    logger.info("🛡️ Cover set for player: %s", _cov or "none")

    # ── Träning / Downtime (5e, P2) ──
    for tr in mech.get("training_update", []):
        if not isinstance(tr, dict):
            continue
        tname = str(tr.get("name", "")).strip()
        try:
            tdays = max(0, int(tr.get("days", 0) or 0))
        except (TypeError, ValueError):
            tdays = 0
        if not tname or tdays <= 0:
            continue
        training = ch.setdefault("training", [])
        if not isinstance(training, list):
            training = []
            ch["training"] = training
        entry = next((e for e in training if str(e.get("name", "")).lower() == tname.lower()), None)
        if entry is None:
            # Ny träning — bara för standard-skills (koden ger proficiency)
            if any(str(s.get("name", "")).lower() == tname.lower() for s in _ensure_skills(ch)):
                entry = {"name": tname, "days_spent": 0, "days_needed": 10, "skill": tname}
                training.append(entry)
            else:
                logger.info("🎓 Training ignored (not a standard skill): %s", tname)
                continue
        entry["days_spent"] = int(entry.get("days_spent", 0) or 0) + tdays
        logger.info("🎓 Training %s: %d/%d days", tname, entry["days_spent"], entry.get("days_needed", 10))
        effects.append({"type": "training_progress", "name": tname, "days": entry["days_spent"]})
        if entry["days_spent"] >= int(entry.get("days_needed", 10) or 10):
            _grant_skill_proficiency(ch, tname)
            effects.append({"type": "training_complete", "skill": tname})
            logger.info("🎓 Training COMPLETE — %s now proficient", tname)
            training.remove(entry)

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
                        logger.info("🛡️ Guardian correction: NPC '%s' removed — %s", removed_npc.get("name", "?"), reason[:80])
                        break
        elif reason:
            effects.append({"type": "korrigering", "value": reason, "reason": reason})
            logger.info("🛡️ Guardian correction: %s — %s", field, reason[:80])

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


def _ensure_hp(ch: dict) -> dict:
    """hp-dict som aldrig är None (audit 2026-09-06 bug 7: `hp: null` i state
    → ch.setdefault ersätter inte null → AttributeError kraschar hela turen)."""
    hp = ch.get("hp")
    if not isinstance(hp, dict):
        hp = {"current": 1, "max": 1, "temp": 0}
        ch["hp"] = hp
    hp.setdefault("current", 1)
    hp.setdefault("max", 1)
    hp.setdefault("temp", 0)
    return hp


def _ensure_xp(ch: dict) -> dict:
    """xp-dict som aldrig är None; next_level från _XP_THRESHOLDS (inte 900)."""
    xp = ch.get("xp")
    if not isinstance(xp, dict):
        xp = {}
        ch["xp"] = xp
    xp.setdefault("current", 0)
    if not xp.get("next_level"):
        level = _safe_int(ch.get("level"), 1)
        xp["next_level"] = _XP_THRESHOLDS[level] if level < len(_XP_THRESHOLDS) else None
    return xp


def _check_level_ups(ch: dict, effects: list) -> int:
    """Level-up-motor (audit 2026-09-06 §5, konsoliderad): WHILE-loop →
    multi-level per tur; next_level alltid från _XP_THRESHOLDS. Anropas
    ovillkorligt (även xp_gain == 0) så att en karaktär som passerat
    tröskeln via tagg-/quest-vägen aldrig sitter fast. Returnerar antalet
    level-ups. _apply_level_up_bonuses är oförändrad (main.py importerar den)."""
    xp = _ensure_xp(ch)
    gained = 0
    while True:
        level = _safe_int(ch.get("level"), 1)
        if level >= len(_XP_THRESHOLDS):
            xp["next_level"] = None
            break
        if _safe_int(xp.get("current"), 0) < _XP_THRESHOLDS[level]:
            xp["next_level"] = _XP_THRESHOLDS[level]
            break
        ch["level"] = level + 1
        xp["next_level"] = _XP_THRESHOLDS[level + 1] if level + 1 < len(_XP_THRESHOLDS) else None
        _apply_level_up_bonuses(ch, effects)
        gained += 1
        logger.info("🛡️ Guardian: LEVEL UP → level %d!", ch["level"])
    return gained


def _repair_truncated_json(text: str) -> str | None:
    """Reparera kapad JSON från reasoning-modeller (portad från main.py,
    audit 2026-09-06 §4 — fanns bara i manuella /guardian-vägen förut).

    Stänger oavslutade citat och lägger till saknade } ] så att fälten
    (items_add, spells_add …) ändå appliceras. Returnerar reparerad text,
    eller None om reparationen inte hjälper.
    """
    s = text.strip()
    if not s:
        return None
    # Redan giltig — returnera som den är
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass
    # Om udda antal oescapede citattecken → oavslutad sträng: stäng den
    quote_count = len(re.findall(r'(?<!\\)"', s))
    if quote_count % 2 == 1:
        s += '"'
    # Balansera { [ mot } ] — stäng i omvänd ordning
    stack = []
    for _c in s:
        if _c in "{[":
            stack.append(_c)
        elif _c in "}]":
            if stack:
                stack.pop()
    for _c in reversed(stack):
        s += "]" if _c == "[" else "}"
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        return None


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

    # Trunkerings-reparation (audit 2026-09-06 §4): reasoning-modeller med låg
    # max_tokens kapar mitt i en sträng → stäng citat/klammer så att mekaniken
    # inte tappas tyst. Fanns tidigare BARA i manuella /guardian-vägen (main.py)
    # — samma logik nu i live post-DM-vägen (_parse_json).
    if start != -1:
        repaired = _repair_truncated_json(cleaned[start:])
        if repaired is not None:
            try:
                data = json.loads(repaired)
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
                "npcs_new", "npc_relations", "npcs_near", "npc_notes", "locations_new",
                "world_lore", "roll_grants", "corrections",
                "initiative_entries", "enemy_actions", "status_apply",
                "player_attacks", "ally_attacks", "ally_damage", "enemy_attacks", "combat_events",
                "spell_slots_spend", "training_update"):
        if not isinstance(mech.get(key), list):
            mech[key] = []

    # Inspiration-fälten ska vara bool (sanera LLM-skriblerier som strängar)
    for _ik in ("inspiration_gain", "inspiration_spend"):
        if not isinstance(mech.get(_ik), bool):
            mech[_ik] = bool(mech.get(_ik))

    # exhaustion_change ska vara int (clamp 0-6-växling hanteras i apply_mechanics)
    try:
        mech["exhaustion_change"] = int(mech.get("exhaustion_change", 0))
    except (TypeError, ValueError):
        mech["exhaustion_change"] = 0

    # cover_set ska vara dict {"target","cover"} eller null
    _cs = mech.get("cover_set")
    if _cs is not None and not isinstance(_cs, dict):
        mech["cover_set"] = None
    elif isinstance(_cs, dict):
        _cov = _cs.get("cover")
        if _cov not in ("half", "three_quarters", "full", None):
            mech["cover_set"] = None

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
    hp = ch.get("hp") or {}
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
                lines.append(f"💔 **{v} damage** → HP {hp.get('current', '?')}/{hp.get('max', '?')}")
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
        elif t == "spell_slots_up":
            label = "Spell slots now:" if en else "Spell slots nu:"
            lines.append(f"🔮 **{label}** {v}")
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
        elif t == "guld_fail":
            denom = e.get("denom", "gp")
            if en:
                lines.append(f"🚫 **Not enough {denom}** — the {v} {denom} purchase is refused; your coins stay.")
            else:
                lines.append(f"🚫 **Inte tillräckligt med {denom}** — {v} {denom} vägras; dina mynt finns kvar.")
        elif t == "status":
            if en:
                lines.append(f"🌀 **Condition:** {v}")
            else:
                lines.append(f"🌀 **Tillstånd:** {v}")
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
            d20 = e.get("d20")
            bonus = e.get("bonus", 0)
            dnot = e.get("damage_dice", "")
            drolls = e.get("damage_rolls", [])
            crit_str = f" {'💥 CRIT!' if crit else ''}"
            if d20 is not None:
                dice_str = f"(🎲 d20={d20}+{bonus}={roll}"
                if drolls:
                    dice_str += f" · {dnot}: [{', '.join(str(x) for x in drolls)}]={dmg})"
                else:
                    dice_str += ")"
            else:
                dice_str = f"(roll {roll})"
            if en:
                lines.append(f"🗡️ **{v}** hits you — **{dmg} damage**{crit_str} {dice_str}")
            else:
                lines.append(f"🗡️ **{v}** träffar dig — **{dmg} skada**{crit_str} {dice_str}")
        elif t == "enemy_miss":
            roll = e.get("roll", "?")
            d20 = e.get("d20")
            bonus = e.get("bonus", 0)
            dice_str = f"(🎲 d20={d20}+{bonus}={roll})" if d20 is not None else f"(roll {roll})"
            if en:
                lines.append(f"🛡️ **{v}** misses you {dice_str}")
            else:
                lines.append(f"🛡️ **{v}** missar dig {dice_str}")
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
            lines.append(f"🔧 **{label}** {v}")
        elif t == "spell_slots_spend":
            sname = e.get("name", "?")
            slvl = e.get("level", "?")
            rem = e.get("remaining", "?")
            smax = (ch.get("spell_slots") or {}).get("max", "?")
            if en:
                lines.append(f"🪄 **{sname}** (level {slvl}) cast — spell slots {rem}/{smax} left")
            else:
                lines.append(f"🪄 **{sname}** (nivå {slvl}) kastad — spell slots {rem}/{smax} kvar")
        elif t == "spell_slots_blocked":
            sname = e.get("name", "?")
            slvl = e.get("level", "?")
            ss = ch.get("spell_slots") or {}
            if en:
                lines.append(f"⛔ **{sname}** (level {slvl}) — not enough spell slots ({ss.get('current', 0)}/{ss.get('max', 0)})")
            else:
                lines.append(f"⛔ **{sname}** (nivå {slvl}) — otillräckliga spell slots ({ss.get('current', 0)}/{ss.get('max', 0)})")
        elif t == "inspiration_gain":
            lines.append("✨ **Inspiration gained!**" if en else "✨ **Inspiration erhållen!**")
        elif t == "inspiration_spend":
            if en:
                lines.append("✨ **Inspiration spent** — advantage on your next roll")
            else:
                lines.append("✨ **Inspiration spenderad** — fördel på nästa kast")
        elif t == "exhaustion":
            lvl = e.get("level", "?")
            extra = f" ({'long rest' if en else 'lång vila'})" if e.get("source") == "long_rest" else ""
            label = "Exhaustion" if en else "Utmattning"
            lines.append(f"🥀 **{label} {lvl}/6**{extra}")
        elif t == "exhaustion_hp_halved":
            if en:
                lines.append(f"🥀 **Exhaustion L4:** HP max halved → {e.get('max', '?')}")
            else:
                lines.append(f"🥀 **Utmattning N4:** HP-max halverat → {e.get('max', '?')}")
        elif t == "exhaustion_recovered":
            if en:
                lines.append(f"🍃 **HP max restored:** {e.get('max', '?')}")
            else:
                lines.append(f"🍃 **HP-max återställt:** {e.get('max', '?')}")
        elif t == "spell_add":
            slvl = e.get("level", 0)
            if en:
                lines.append(f"📜 **Spell learned:** {v} (level {slvl})")
            else:
                lines.append(f"📜 **Ny besvärjelse:** {v} (nivå {slvl})")
        elif t == "vila" and not mech.get("rest"):
            # Kort-vila-effekten — renderas bara här om mech.rest-blocket nedan
            # inte redan täckt den (undvik dubbla "Kort vila"-rader)
            detail = e.get("detail", "")
            if en:
                lines.append(f"⛺ **Short rest:** {detail}" if detail else "⛺ **Short rest**")
            else:
                lines.append(f"⛺ **Kort vila:** {detail}" if detail else "⛺ **Kort vila**")
        elif t == "training_progress":
            tname = e.get("name", "?")
            days = e.get("days", "?")
            if en:
                lines.append(f"🎓 **Training ({tname}):** {days} days completed")
            else:
                lines.append(f"🎓 **Träning ({tname}):** {days} dagar avklarade")
        elif t == "training_complete":
            skill = e.get("skill", "?")
            if en:
                lines.append(f"🎓 **Training complete:** {skill} — you are now proficient")
            else:
                lines.append(f"🎓 **Träning klar:** {skill} — du är nu proficient")
        elif t == "cover_set":
            cov = e.get("cover")
            _cov_sv = {"half": "halv täckning (+2 AC)", "three_quarters": "tre fjärdedels täckning (+5 AC)", "full": "full täckning — kan inte träffas", None: "ingen täckning"}
            _cov_en = {"half": "half cover (+2 AC)", "three_quarters": "three-quarters cover (+5 AC)", "full": "full cover — cannot be targeted", None: "no cover"}
            if en:
                lines.append(f"🧱 **Cover:** {_cov_en.get(cov, cov)}")
            else:
                lines.append(f"🧱 **Täckning:** {_cov_sv.get(cov, cov)}")
        elif t == "npc_near":
            lines.append(f"👥 **{v}**")

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
            & {"combat_start", "combat_dmg", "combat_round", "enemy_död", "initiativ", "combat_end", "skada", "hela", "ally_add", "ally_dmg", "ally_död",
               # audit 2026-09-06 bug 4: kod-rullade fiendeattacker ger enemy_hit/
               # enemy_miss (inte "skada") → taggen måste firea för dem också
               "enemy_hit", "enemy_miss", "enemy_fled", "status_dmg", "status_end"}
        ) or any(mech.get(k) for k in ("combat_start", "combat_round", "initiative_entries", "combat_end",
                                        "player_attacks", "enemy_attacks", "ally_attacks", "ally_damage", "combat_events"))
        _just_ended = combat.get("active") is False and combat.get("ended_turn") == state.get("meta", {}).get("turn_count", 0)
        if _changed or _just_ended:
            # Include player HP so the frontend status bar + inline messages can show it
            ch = state.get("character", {})
            php = ch.get("hp") or {}
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
