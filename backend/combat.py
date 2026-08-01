"""
Combat Engine — Mörkrets Rikes stridsmotor
===========================================
Hanterar turordning, action economy, status-effekter, fiende-AI,
flykt och alla mekaniska aspekter av strid.

Design:
  - combat.py ÄGER all stridslogik. Guardian extraherar, DM narrerar.
  - Varje combatant har: 1 action + 1 bonus action + 1 reaktion per runda.
  - Status-effekter har duration och rensas automatiskt.
  - Fiender rullar attack mot spelarens AC (inte bara narrativ skada).
  - Initiativ sorteras fallande; turordningen roterar varje runda.

Datastruktur (world.combat):
  {
    "active": true,
    "round": 1,
    "phase": "player" | "enemies" | "round_end",
    "turn_order": [{"key": "player", "name": "...", "initiative": 15, "acted": false}],
    "current_index": 0,
    "enemies": [{id, name, hp, max_hp, ac, alive, statuses, attack_bonus, damage_dice}],
    "player_actions": {"action": true, "bonus": true, "reaction": true},
    "log": [],
    "started_turn": N,
    "ended_turn": null,
  }
"""

from __future__ import annotations

import json
import logging
import random
import re
from urllib.parse import quote

logger = logging.getLogger("morkrets.combat")

# ═══════════════════════════════════════
# TÄRNINGAR
# ═══════════════════════════════════════

def roll_dice(notation: str) -> tuple[int, list[int]]:
    """Rulla tärningsnotation (t.ex. '2d6+3'). Returnerar (total, [rolls])."""
    notation = notation.strip().lower().replace(" ", "")
    m = re.match(r"^(\d+)d(\d+)([+-]\d+)?$", notation)
    if not m:
        # Fallback: försök extrahera siffror
        nums = re.findall(r"\d+", notation)
        if len(nums) >= 2:
            count, sides = int(nums[0]), int(nums[1])
        else:
            return 0, []
        mod = 0
    else:
        count, sides = int(m.group(1)), int(m.group(2))
        mod = int(m.group(3) or 0)
    rolls = [random.randint(1, sides) for _ in range(count)]
    return sum(rolls) + mod, rolls


def roll_d20() -> int:
    return random.randint(1, 20)


# ═══════════════════════════════════════
# STATUS-EFFEKTER
# ═══════════════════════════════════════

# Varje status: {"name": str, "duration": int (rundor), "dmg_per_turn": int, "type": str}
STATUS_DEFS = {
    "poison":    {"dmg_per_turn": 2, "attack_disadvantage": True,  "save_disadvantage": True},
    "burn":      {"dmg_per_turn": 3, "attack_disadvantage": False, "save_disadvantage": False},
    "bleed":     {"dmg_per_turn": 1, "attack_disadvantage": False, "save_disadvantage": False},
    "stun":      {"dmg_per_turn": 0, "attack_disadvantage": True,  "save_disadvantage": True, "skip_turn": True},
    "frighten":  {"dmg_per_turn": 0, "attack_disadvantage": True,  "save_disadvantage": False},
    "prone":     {"dmg_per_turn": 0, "attack_disadvantage": True,  "save_disadvantage": False},
    "charm":     {"dmg_per_turn": 0, "attack_disadvantage": False, "save_disadvantage": False},
    "blind":     {"dmg_per_turn": 0, "attack_disadvantage": True,  "save_disadvantage": False},
    "restrain":  {"dmg_per_turn": 0, "attack_disadvantage": True,  "save_disadvantage": True},
}


def add_status(entity: dict, name: str, duration: int = 2, dmg_override: int | None = None) -> bool:
    """Lägg till en status-effekt på en entity (fiende eller spelare).
    Returnerar True om statusen lades till (inte redan finns)."""
    statuses = entity.setdefault("statuses", [])
    existing = next((s for s in statuses if s.get("name") == name), None)
    if existing:
        # Förläng duration
        existing["duration"] = max(existing.get("duration", 1), duration)
        return False
    defn = STATUS_DEFS.get(name, {})
    statuses.append({
        "name": name,
        "duration": duration,
        "dmg_per_turn": dmg_override if dmg_override is not None else defn.get("dmg_per_turn", 0),
    })
    return True


def tick_statuses(entity: dict) -> list[dict]:
    """Applicera status-skada och minska duration. Returnerar effekter."""
    effects = []
    statuses = entity.get("statuses", [])
    remaining = []
    for s in statuses:
        dmg = s.get("dmg_per_turn", 0)
        if dmg > 0:
            hp = entity.get("hp", 0)
            entity["hp"] = max(0, hp - dmg)
            effects.append({"type": "status_dmg", "status": s["name"], "amount": dmg})
        s["duration"] = s.get("duration", 1) - 1
        if s["duration"] > 0:
            remaining.append(s)
        else:
            effects.append({"type": "status_end", "status": s["name"]})
    entity["statuses"] = remaining
    return effects


def has_status(entity: dict, name: str) -> bool:
    return any(s.get("name") == name for s in entity.get("statuses", []))


def has_disadvantage(entity: dict) -> bool:
    """Har entityn någon status som ger nackdel på attacker?"""
    for s in entity.get("statuses", []):
        defn = STATUS_DEFS.get(s.get("name", ""), {})
        if defn.get("attack_disadvantage"):
            return True
    return False


def is_stunned(entity: dict) -> bool:
    return has_status(entity, "stun")


# ═══════════════════════════════════════
# STRIDSSTART
# ═══════════════════════════════════════

def start_combat(state: dict, enemies_in: list[dict]) -> dict:
    """Initiera en ny strid. Skapar world.combat med fiender.

    enemies_in: [{"name": "Goblin", "hp": 7, "ac": 12, "attack_bonus": 4, "damage_dice": "1d6+2"}]
    """
    world = state.setdefault("world", {})
    enemies = []
    for i, e in enumerate(enemies_in):
        name = (e.get("name") or f"Fiende {i+1}").strip()
        hp = max(1, int(e.get("hp", 7)))
        enemies.append({
            "id": i,
            "name": name,
            "hp": hp,
            "max_hp": hp,
            "ac": int(e.get("ac", 10)),
            "alive": True,
            "statuses": [],
            "attack_bonus": int(e.get("attack_bonus", 3)),
            "damage_dice": e.get("damage_dice", "1d6+1"),
            "actions_remaining": 1,
        })

    combat = {
        "active": True,
        "round": 1,
        "phase": "awaiting_initiative",  # väntar på initiativslag
        "turn_order": [],
        "current_index": 0,
        "enemies": enemies,
        "player_actions": {"action": True, "bonus": True, "reaction": True},
        "log": [],
        "started_turn": state.get("meta", {}).get("turn_count", 0),
        "ended_turn": None,
    }
    world["combat"] = combat
    logger.info("⚔️ Strid startad: %s", ", ".join(e["name"] for e in enemies))
    return combat


# ═══════════════════════════════════════
# INITIATIV
# ═══════════════════════════════════════

def roll_initiative(state: dict, player_roll: int | None = None) -> dict:
    """Slå initiativ för alla deltagare. Sortera fallande.

    player_roll: spelarens initiativslag (1d20+mod). Om None, slå automatiskt.
    Returnerar combat-dict med uppdaterad turn_order.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return combat or {}

    char = state.get("character", {})
    pname = char.get("name", "Spelaren")
    init_mod = int(char.get("initiative", 0))

    if player_roll is None:
        player_roll = roll_d20() + init_mod

    turn_order = [{"key": "player", "name": pname, "initiative": player_roll, "acted": False}]

    for enemy in combat.get("enemies", []):
        if not enemy.get("alive", True):
            continue
        # Fiendeinitiativ: 1d20 + attack_bonus (approximation av DEX)
        enemy_init = roll_d20() + enemy.get("attack_bonus", 0)
        turn_order.append({
            "key": f"enemy:{enemy['id']}",
            "name": enemy["name"],
            "initiative": enemy_init,
            "acted": False,
        })

    # Sortera fallande (högst först)
    turn_order.sort(key=lambda x: x.get("initiative", 0), reverse=True)

    combat["turn_order"] = turn_order
    combat["current_index"] = 0
    combat["phase"] = "combat"

    # Logga
    order_str = " → ".join(f"{e['name']}({e['initiative']})" for e in turn_order)
    combat.setdefault("log", []).append({
        "round": 1, "actor": "system", "name": "",
        "text": f"Initiativ: {order_str}",
    })
    logger.info("🎲 Initiativ: %s", order_str)
    return combat


# ═══════════════════════════════════════
# TURORDNING
# ═══════════════════════════════════════

def get_current_actor(combat: dict) -> dict | None:
    """Vem är det som agerar just nu?"""
    order = combat.get("turn_order", [])
    idx = combat.get("current_index", 0)
    if not order or idx >= len(order):
        return None
    return order[idx]


def is_player_turn(combat: dict) -> bool:
    actor = get_current_actor(combat)
    return actor is not None and actor.get("key") == "player"


def advance_turn(state: dict) -> dict:
    """Gå till nästa tur. Hanterar rundövergångar och status-tick.

    Returnerar combat-dict. Anropas efter att en combatant agerat.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return combat or {}

    order = combat.get("turn_order", [])
    if not order:
        return combat

    # Markera nuvarande som acted
    idx = combat.get("current_index", 0)
    if idx < len(order):
        order[idx]["acted"] = True

    # Hitta nästa levande deltagare
    next_idx = idx + 1
    while next_idx < len(order):
        entry = order[next_idx]
        key = entry.get("key", "")
        if key == "player":
            break
        # Fiende — kolla att den lever
        eid = int(key.split(":")[1]) if ":" in key else -1
        enemy = next((e for e in combat.get("enemies", []) if e["id"] == eid), None)
        if enemy and enemy.get("alive", True):
            break
        next_idx += 1

    if next_idx >= len(order):
        # Ny runda
        combat["round"] = combat.get("round", 1) + 1
        combat["current_index"] = 0
        # Återställ acted-flaggor
        for entry in order:
            entry["acted"] = False
        # Återställ player actions
        combat["player_actions"] = {"action": True, "bonus": True, "reaction": True}
        # Återställ fiende actions
        for enemy in combat.get("enemies", []):
            if enemy.get("alive", True):
                enemy["actions_remaining"] = 1
        # Ticka status-effekter på alla
        _tick_all_statuses(state, combat)
        combat.setdefault("log", []).append({
            "round": combat["round"], "actor": "system", "name": "",
            "text": f"Runda {combat['round']} börjar",
        })
        logger.info("⚔️ Runda %d", combat["round"])
    else:
        combat["current_index"] = next_idx

    # Kolla om striden är över (alla fiender döda)
    _check_combat_end(state, combat)

    return combat


def _tick_all_statuses(state: dict, combat: dict):
    """Ticka status-effekter på alla combatants vid rundstart."""
    # Spelaren
    char = state.get("character", {})
    player_entity = {"hp": char.get("hp", {}).get("current", 0), "statuses": char.get("statuses", [])}
    status_fx = tick_statuses(player_entity)
    if status_fx:
        char.setdefault("hp", {})["current"] = player_entity["hp"]
        char["statuses"] = player_entity["statuses"]
        for fx in status_fx:
            if fx["type"] == "status_dmg":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": char.get("name", "Spelaren"),
                    "text": f"tar {fx['amount']} {fx['status']}-skada",
                })

    # Fiender
    for enemy in combat.get("enemies", []):
        if not enemy.get("alive", True):
            continue
        fx = tick_statuses(enemy)
        for f in fx:
            if f["type"] == "status_dmg":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": enemy["name"],
                    "text": f"tar {f['amount']} {f['status']}-skada",
                })
            elif f["type"] == "status_end":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": enemy["name"],
                    "text": f"{f['status']} avtar",
                })
        if enemy["hp"] <= 0:
            enemy["alive"] = False
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "system",
                "name": enemy["name"], "text": "faller",
            })


# ═══════════════════════════════════════
# SPELARENS AKTIONER
# ═══════════════════════════════════════

def player_attack(state: dict, target_id: int, attack_roll: int, damage_notation: str) -> dict:
    """Spelaren attackerar en fiende.

    attack_roll: spelarens 1d20+mod resultat.
    damage_notation: skadetärning (t.ex. '1d8+2').
    Returnerar resultat-dict.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return {"hit": False, "error": "Ingen aktiv strid"}

    enemy = next((e for e in combat.get("enemies", []) if e["id"] == target_id and e.get("alive", True)), None)
    if not enemy:
        return {"hit": False, "error": "Ogiltigt mål"}

    # Kolla action
    pa = combat.get("player_actions", {})
    if not pa.get("action", True):
        return {"hit": False, "error": "Ingen action kvar denna runda"}

    # Nat 20 / Nat 1
    nat_roll = attack_roll  # anta att frontend skickar den råa d20 + mod
    # Vi behöver veta den råa d20 — frontend skickar total. Anta nat = total - mod.
    # Bättre: frontend skickar {d20: X, total: Y}. För nu: hantera bara total.
    is_crit = False  # TODO: frontend skickar raw d20
    is_fumble = False

    ac = enemy.get("ac", 10)
    hit = attack_roll >= ac or is_crit

    result = {
        "hit": hit,
        "crit": is_crit,
        "fumble": is_fumble,
        "attack_roll": attack_roll,
        "target_ac": ac,
        "target": enemy["name"],
        "damage": 0,
        "damage_rolls": [],
    }

    if hit:
        dmg, rolls = roll_dice(damage_notation)
        if is_crit:
            # Dubbla skadetärningar
            dmg2, rolls2 = roll_dice(damage_notation)
            dmg += dmg2
            rolls += rolls2
        dmg = max(1, dmg)
        enemy["hp"] = max(0, enemy.get("hp", 0) - dmg)
        result["damage"] = dmg
        result["damage_rolls"] = rolls

        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "player",
            "name": state.get("character", {}).get("name", "Spelaren"),
            "text": f"träffar {enemy['name']} — {dmg} skada (AC {ac}, slag {attack_roll})",
        })

        if enemy["hp"] <= 0:
            enemy["alive"] = False
            result["killed"] = True
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "system",
                "name": enemy["name"], "text": "faller",
            })
            logger.info("💀 %s besegrad", enemy["name"])
    else:
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "player",
            "name": state.get("character", {}).get("name", "Spelaren"),
            "text": f"missar {enemy['name']} (slag {attack_roll} mot AC {ac})",
        })

    # Förbruka action
    pa["action"] = False
    combat["player_actions"] = pa

    _check_combat_end(state, combat)
    return result


def player_cast_spell(state: dict, target_id: int | None, spell_name: str,
                      attack_roll: int | None = None, save_dc: int | None = None,
                      damage_notation: str | None = None, slot_level: int = 1) -> dict:
    """Spelaren kastar en besvärjelse. Drar spell slot."""
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return {"success": False, "error": "Ingen aktiv strid"}

    char = state.get("character", {})
    ss = char.get("spell_slots", {})
    if ss.get("current", 0) < slot_level:
        return {"success": False, "error": "Otillräckliga spell slots"}

    pa = combat.get("player_actions", {})
    if not pa.get("action", True):
        return {"success": False, "error": "Ingen action kvar"}

    # Dra spell slot
    ss["current"] = ss.get("current", 0) - slot_level
    char["spell_slots"] = ss
    pa["action"] = False
    combat["player_actions"] = pa

    result = {"success": True, "spell": spell_name, "slot_used": slot_level}

    if target_id is not None and damage_notation:
        enemy = next((e for e in combat.get("enemies", []) if e["id"] == target_id and e.get("alive")), None)
        if enemy:
            if attack_roll is not None:
                hit = attack_roll >= enemy.get("ac", 10)
                result["hit"] = hit
                if hit:
                    dmg, rolls = roll_dice(damage_notation)
                    enemy["hp"] = max(0, enemy["hp"] - dmg)
                    result["damage"] = dmg
                    if enemy["hp"] <= 0:
                        enemy["alive"] = False
                        result["killed"] = True
            else:
                # Save-based: anta att fienden misslyckas (DM/Guardian avgör)
                dmg, rolls = roll_dice(damage_notation)
                enemy["hp"] = max(0, enemy["hp"] - dmg)
                result["damage"] = dmg
                if enemy["hp"] <= 0:
                    enemy["alive"] = False
                    result["killed"] = True

    combat.setdefault("log", []).append({
        "round": combat.get("round", 1), "actor": "player",
        "name": char.get("name", "Spelaren"),
        "text": f"kastar {spell_name}",
    })

    _check_combat_end(state, combat)
    return result


def player_use_bonus_action(state: dict, action_name: str) -> dict:
    """Spelaren använder sin bonus action."""
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return {"success": False, "error": "Ingen aktiv strid"}
    pa = combat.get("player_actions", {})
    if not pa.get("bonus", True):
        return {"success": False, "error": "Bonus action redan använd"}
    pa["bonus"] = False
    combat["player_actions"] = pa
    combat.setdefault("log", []).append({
        "round": combat.get("round", 1), "actor": "player",
        "name": state.get("character", {}).get("name", "Spelaren"),
        "text": f"bonus action: {action_name}",
    })
    return {"success": True, "action": action_name}


# ═══════════════════════════════════════
# FIENDE-AI (Battle Guardian)
# ═══════════════════════════════════════

def enemy_turn(state: dict, enemy: dict) -> dict:
    """En fiendes tur. Rullar attack mot spelarens AC och slår skada.

    Returnerar resultat-dict med alla fiendens handlingar.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return {"actions": []}

    char = state.get("character", {})
    player_ac = int(char.get("ac", 10))
    player_name = char.get("name", "Spelaren")
    results = []

    # Stun-check: hoppa över tur
    if is_stunned(enemy):
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "enemy",
            "name": enemy["name"], "text": "är bedövad och kan inte agera",
        })
        return {"actions": [], "stunned": True}

    # Har fienden disadvantage från status?
    disadv = has_disadvantage(enemy)

    actions_left = enemy.get("actions_remaining", 1)
    while actions_left > 0 and enemy.get("alive", True):
        # Rulla attack
        d20 = roll_d20()
        if disadv:
            d20_2 = roll_d20()
            d20 = min(d20, d20_2)  # nackdel: ta sämsta

        attack_bonus = enemy.get("attack_bonus", 3)
        total = d20 + attack_bonus
        hit = total >= player_ac or d20 == 20
        crit = d20 == 20
        fumble = d20 == 1

        action_result = {
            "attack_roll": total,
            "d20": d20,
            "target_ac": player_ac,
            "hit": hit,
            "crit": crit,
            "fumble": fumble,
            "damage": 0,
        }

        if fumble:
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "enemy",
                "name": enemy["name"],
                "text": f"missar {player_name} (nat 1!)",
            })
        elif hit:
            dmg_notation = enemy.get("damage_dice", "1d6+1")
            dmg, rolls = roll_dice(dmg_notation)
            if crit:
                dmg2, rolls2 = roll_dice(dmg_notation)
                dmg += dmg2
            dmg = max(1, dmg)

            # Applicera skada på spelaren
            hp = char.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
            temp = hp.get("temp", 0)
            if temp > 0:
                absorbed = min(temp, dmg)
                hp["temp"] = temp - absorbed
                dmg -= absorbed
            hp["current"] = max(0, hp.get("current", 1) - dmg)

            action_result["damage"] = dmg
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "enemy",
                "name": enemy["name"],
                "text": f"träffar {player_name} — {dmg} skada{' (KRITISK!)' if crit else ''} (slag {total} mot AC {player_ac})",
            })
            logger.info("⚔️ %s → %s: %d skada (AC %d)", enemy["name"], player_name, dmg, player_ac)
        else:
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "enemy",
                "name": enemy["name"],
                "text": f"missar {player_name} (slag {total} mot AC {player_ac})",
            })

        results.append(action_result)
        actions_left -= 1

    enemy["actions_remaining"] = 0
    return {"actions": results}


def run_all_enemy_turns(state: dict) -> list[dict]:
    """Kör alla fienders turer i sekvens. Returnerar alla resultat."""
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return []

    all_results = []
    for enemy in combat.get("enemies", []):
        if not enemy.get("alive", True):
            continue
        result = enemy_turn(state, enemy)
        all_results.append({"enemy": enemy["name"], **result})
        # Kolla om spelaren dog
        char = state.get("character", {})
        if char.get("hp", {}).get("current", 1) <= 0:
            break

    _check_combat_end(state, combat)
    return all_results


# ═══════════════════════════════════════
# FLYKT
# ═══════════════════════════════════════

def attempt_flee(state: dict, dex_check: int) -> dict:
    """Spelaren försöker fly. DEX-check mot DC 10 + antal fiender.

    Returnerar {"success": bool, "dc": int, "roll": int}.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return {"success": False, "error": "Ingen aktiv strid"}

    alive_enemies = [e for e in combat.get("enemies", []) if e.get("alive", True)]
    dc = 10 + len(alive_enemies)
    success = dex_check >= dc

    if success:
        end_combat(state, "spelaren flydde")
        logger.info("🏃 Player fled from combat (roll %d vs DC %d)", dex_check, dc)
    else:
        combat.setdefault("log", []).append({
            "round": combat.get("round", 1), "actor": "player",
            "name": state.get("character", {}).get("name", "Spelaren"),
            "text": f"försöker fly men misslyckas (slag {dex_check} mot DC {dc})",
        })
        # Fienderna får en extra attack (opportunity)
        logger.info("🏃 Flykt misslyckades (slag %d mot DC %d)", dex_check, dc)

    return {"success": success, "dc": dc, "roll": dex_check}


# ═══════════════════════════════════════
# STRIDSSLUT
# ═══════════════════════════════════════

def end_combat(state: dict, reason: str = "striden avslutades") -> dict:
    """Avsluta striden. Rensar combat-state."""
    combat = state.get("world", {}).get("combat")
    if not combat:
        return {}

    combat["active"] = False
    combat["ended_turn"] = state.get("meta", {}).get("turn_count", 0)
    combat.setdefault("log", []).append({
        "round": combat.get("round", 1), "actor": "system", "name": "",
        "text": f"Striden är över — {reason}",
    })

    # Rensa spelarens status-effekter
    char = state.get("character", {})
    char.pop("statuses", None)

    logger.info("🏁 Combat over: %s", reason)
    return combat


def _check_combat_end(state: dict, combat: dict):
    """Auto-avsluta om alla fiender är döda."""
    if not combat.get("active"):
        return
    enemies = combat.get("enemies", [])
    if enemies and all(not e.get("alive", True) for e in enemies):
        end_combat(state, "alla fiender besegrade")


# ═══════════════════════════════════════
# [COMBAT:]-TAGG FÖR FRONTEND
# ═══════════════════════════════════════

def combat_tag(combat: dict) -> str:
    """Generera [COMBAT:<urlencoded-json>]-tagg för frontendens Krigsråd."""
    try:
        return f"[COMBAT:{quote(json.dumps(combat, ensure_ascii=False), safe='')}]"
    except Exception:
        return ""


def build_combat_context(state: dict, language: str = "sv") -> str:
    """Bygg en kompakt stridskontext för DM-prompten."""
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return ""

    char = state.get("character", {})
    hp = char.get("hp", {})
    en = language == "en"

    lines = []
    if en:
        lines.append(f"## ⚔️ COMBAT — Round {combat.get('round', 1)}")
    else:
        lines.append(f"## ⚔️ STRID — Runda {combat.get('round', 1)}")

    # Turordning
    order = combat.get("turn_order", [])
    if order:
        current = get_current_actor(combat)
        order_parts = []
        for entry in order:
            marker = "→ " if current and entry.get("key") == current.get("key") else "  "
            acted = " ✓" if entry.get("acted") else ""
            order_parts.append(f"{marker}{entry['name']}({entry['initiative']}){acted}")
        if en:
            lines.append(f"Turn order: {' | '.join(order_parts)}")
        else:
            lines.append(f"Turordning: {' | '.join(order_parts)}")

    # Fiender
    enemies = [e for e in combat.get("enemies", []) if e.get("alive", True)]
    if enemies:
        e_parts = []
        for e in enemies:
            status_str = ""
            if e.get("statuses"):
                status_str = " [" + ", ".join(s["name"] for s in e["statuses"]) + "]"
            e_parts.append(f"{e['name']} ({e['hp']}/{e['max_hp']} HP, AC {e['ac']}){status_str}")
        if en:
            lines.append(f"Enemies: {', '.join(e_parts)}")
        else:
            lines.append(f"Fiender: {', '.join(e_parts)}")

    # Spelarens resurser
    pa = combat.get("player_actions", {})
    ss = char.get("spell_slots", {})
    action_str = f"Action: {'✓' if pa.get('action') else '✗'} | Bonus: {'✓' if pa.get('bonus') else '✗'} | Reaction: {'✓' if pa.get('reaction') else '✗'}"
    lines.append(f"HP: {hp.get('current', '?')}/{hp.get('max', '?')} · AC: {char.get('ac', '?')} · {action_str}")
    if ss.get("max", 0) > 0:
        lines.append(f"Spell slots: {ss.get('current', 0)}/{ss.get('max', 0)}")

    # Spelarens status
    player_statuses = char.get("statuses", [])
    if player_statuses:
        s_str = ", ".join(f"{s['name']}({s.get('duration', '?')}r)" for s in player_statuses)
        lines.append(f"Status: {s_str}")

    return "\n".join(lines)
