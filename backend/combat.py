"""
Combat Engine — The Lore Weaver's Cauldron's stridsmotor
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
    "allies": [{id, name, hp, max_hp, ac, alive, statuses, attack_bonus, damage_dice}],
    "player_actions": {"action": true, "bonus": true, "reaction": true},
    "log": [],
    "started_turn": N,
    "ended_turn": null,
  }
"""

from __future__ import annotations

import json
import logging
import secrets
import re
from urllib.parse import quote

logger = logging.getLogger("loreweavers.combat")

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
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return sum(rolls) + mod, rolls


def roll_d20() -> int:
    return secrets.randbelow(20) + 1


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


def add_status(entity: dict, name: str, duration: int = 2, dmg_override: int | None = None,
               save_dc: int | None = None) -> bool:
    """Lägg till en status-effekt på en entity (fiende eller spelare).

    Refresh-not-stack (P1b §3.1.5): omapplicering FÖRLÄNGER duration (max av
    gammalt och nytt) och dmg_per_turn läggs ALDRIG till igen — 5e-villkor
    staplar inte på sig själva. En HÖGRE save_dc lyfter DC:n (värsta-fallets-
    regeln), en lägre ändrar inget. Duration klampas 1–10 (§3.1.1).
    Returnerar True om statusen var ny (False = refresh av befintlig)."""
    duration = max(1, min(10, int(duration)))
    statuses = entity.setdefault("statuses", [])
    existing = next((s for s in statuses if s.get("name") == name), None)
    if existing:
        # Förläng duration (refresh — aldrig stack)
        existing["duration"] = max(existing.get("duration", 1), duration)
        if save_dc is not None:
            try:
                existing["save_dc"] = max(int(existing.get("save_dc") or 0), int(save_dc))
            except (TypeError, ValueError):
                pass
        return False
    defn = STATUS_DEFS.get(name, {})
    entry = {
        "name": name,
        "duration": duration,
        "dmg_per_turn": dmg_override if dmg_override is not None else defn.get("dmg_per_turn", 0),
    }
    if save_dc is not None:
        try:
            entry["save_dc"] = max(5, min(25, int(save_dc)))
        except (TypeError, ValueError):
            pass
    statuses.append(entry)
    return True


# 5e-damage-typer (normaliserade, lowercase)
DAMAGE_TYPES = (
    "bludgeoning", "piercing", "slashing", "fire", "cold", "acid", "poison",
    "lightning", "thunder", "radiant", "necrotic", "psychic", "force",
)


def damage_multiplier(damage_type: str, entity: dict) -> float:
    """5e resistans/sårbarhet/immunitet → skademultiplikator.

    entity kan vara character (har resistances/vulnerabilities/immunities) eller
    en fiende/ally (samma fält). Okänd/olista typ → 1.0 (ingen modifiering).
    """
    if not damage_type or not isinstance(damage_type, str):
        return 1.0
    t = damage_type.strip().lower()
    if t not in DAMAGE_TYPES:
        return 1.0
    imm = entity.get("immunities") or []
    if any(str(i).strip().lower() == t for i in imm):
        return 0.0
    res = entity.get("resistances") or []
    if any(str(r).strip().lower() == t for r in res):
        return 0.5
    vul = entity.get("vulnerabilities") or []
    if any(str(v).strip().lower() == t for v in vul):
        return 2.0
    return 1.0


# Status → 5e-damagetyp (för resistans i tick_statuses)
_STATUS_DAMAGE_TYPES = {
    "poison": "poison",
    "burn": "fire",
    "bleed": "slashing",
}


def tick_statuses(entity: dict) -> list[dict]:
    """Applicera status-skada och minska duration. Returnerar effekter."""
    effects = []
    statuses = entity.get("statuses", [])
    remaining = []
    for s in statuses:
        dmg = s.get("dmg_per_turn", 0)
        if dmg > 0:
            # Resistans/sårbarhet (5e, P2): poison→poison, burn→fire, bleed→slashing
            dmg_type = _STATUS_DAMAGE_TYPES.get(s.get("name", ""), "")
            mult = damage_multiplier(dmg_type, entity)
            dmg = int(dmg * mult)
            if dmg > 0:
                hp = entity.get("hp", 0)
                entity["hp"] = max(0, hp - dmg)
                effects.append({"type": "status_dmg", "status": s["name"], "amount": dmg})
            else:
                effects.append({"type": "status_resisted", "status": s["name"], "damage_type": dmg_type or "unknown"})
        s["duration"] = s.get("duration", 1) - 1
        if s["duration"] > 0:
            remaining.append(s)
        else:
            effects.append({"type": "status_end", "status": s["name"]})
    entity["statuses"] = remaining
    return effects


def has_disadvantage(entity: dict) -> bool:
    """Har entityn någon status som ger nackdel på attacker?"""
    for s in entity.get("statuses", []):
        defn = STATUS_DEFS.get(s.get("name", ""), {})
        if defn.get("attack_disadvantage"):
            return True
    return False


# ═══════════════════════════════════════
# STATUS-SPARPROV (P1b §3.1.4) — slut-av-tur, server-rullade
# ═══════════════════════════════════════

def roll_status_saves(entity: dict, *, is_player: bool = False, target: str = "",
                      rng=None) -> list[dict]:
    """Sparprov i slutet av drabbad parts tur för statusar med save_dc.

    Fiender/allierade: server-rullat d20 + 0 (proficiency-löst) vs save_dc —
    rng-sömen enligt enemy_rolls-mönstret (default: modul-globala roll_d20(),
    monkeypatch-vänlig; injicera ett objekt med randbelow(n) för determinism).
    Vid lyckat spår tas statusen bort (status_end). Spelaren rullar ALDRIG
    här — ytorna är status_save_request-effekter som DM:en/frontenden kan
    förvandla till [KAST: … SPAR DC N] (dice-lock).

    Returnerar effekter (status_save / status_end / status_save_request).
    """
    fx: list[dict] = []
    for s in list(entity.get("statuses", [])):
        try:
            dc = int(s.get("save_dc") or 0)
        except (TypeError, ValueError):
            continue
        if dc <= 0:
            continue
        name = str(s.get("name", "?"))
        who = target or ("player" if is_player else str(entity.get("name", "?")))
        if is_player:
            fx.append({"type": "status_save_request", "status": name, "target": who, "dc": dc})
            continue
        d20 = roll_d20() if rng is None else rng.randbelow(20) + 1
        success = d20 >= dc
        fx.append({"type": "status_save", "status": name, "target": who,
                   "d20": d20, "dc": dc, "success": success})
        if success:
            try:
                entity.get("statuses", []).remove(s)
            except ValueError:
                pass
            fx.append({"type": "status_end", "status": name, "d20": d20, "dc": dc})
    return fx


def remove_status(entity: dict, name: str) -> bool:
    """Ta bort en status vid namn (sparprovets framgång, §3.1.4).
    True om en status togs bort."""
    statuses = entity.get("statuses", [])
    for s in list(statuses):
        if s.get("name") == name:
            statuses.remove(s)
            return True
    return False


# ═══════════════════════════════════════
# FLYKT / JAKT (P1b §2) — 3/3-ferdighetsklocka
# ═══════════════════════════════════════

CHASE_SUCCESSES = 3    # klockans mål: 3 framgångar = undkommen (§2.2)
CHASE_MAX_ROUNDS = 6   # klockan MÅSTE lösas — max antal jaktrundor
CHASE_OUTCOMES = ("escape", "caught", "stalemate")


def start_chase(combat: dict, mode: str = "player_flee", quarry: str = "player") -> dict | None:
    """Starta jaktklockan (§2.1–2.2) på combat-dicten.

    Double-start-guard (§4.3 — speglar _end_combat): pågående jakt → no-op.
    En jakt får bara starta när striden är aktiv (§2.3). Returnerar
    chase-dicten, eller None när starten ignorerades."""
    if not (combat and combat.get("active")):
        return None
    chase = combat.get("chase")
    if isinstance(chase, dict) and chase.get("active"):
        return None
    if mode not in ("player_flee", "enemy_flee"):
        mode = "player_flee" if str(quarry).lower() in ("player", "spelaren") else "enemy_flee"
    chase = {"active": True, "mode": mode,
             "successes": 0, "failures": 0, "target": CHASE_SUCCESSES,
             "started_round": combat.get("round", 1),
             "quarry": quarry, "rounds": 0, "result": None}
    combat["chase"] = chase
    combat.setdefault("log", []).append({
        "round": combat.get("round", 1), "actor": "system", "name": "",
        "text": (f"chase begins — {quarry} tries to break away "
                 f"({CHASE_SUCCESSES} escapes / {CHASE_SUCCESSES} catches)"),
    })
    return chase


def tick_chase(state: dict, combat: dict, outcome: str, effects: list | None = None) -> dict | None:
    """Ticka jaktklockan ett jaktrunda (§2.2) — chase_progress-utfall:

    "escape" = bytet vann rundans tävling (+1 framgång) · "caught" =
    förföljaren vann (+1 motgång) · "stalemate" = oavgjort (komplicerad runda,
    klockan står still).

    Fullbordande: 3 framgångar → undkommen, striden avslutas GENOM
    guardian._end_combat ("player fled" / "enemies fled" — alla slutvägar går
    via det gemensamma hjälpet, double-end-guard inbyggd, §2.3). 3 motgångar →
    infångad: jakten stängs, striden går vidare och combat["caught_side"] sätts
    som engångsfördel för förföljarens nästa attack. Kapp-lopp: vid
    CHASE_MAX_ROUNDS rundor avgörs det på kvarstående klocka — oavgjort = bytet
    undkommer MED kostnad (halva det burna guldet droppas, §2.2).

    Returnerar chase-dicten, eller None vid no-op (ingen aktiv jakt, striden
    avslutad eller okänt utfall)."""
    fx = effects if effects is not None else []
    chase = (combat or {}).get("chase")
    if not (combat and combat.get("active") and isinstance(chase, dict) and chase.get("active")):
        return None
    outcome = str(outcome or "").strip().lower()
    if outcome not in CHASE_OUTCOMES:
        logger.warning("🏃 Chase tick dropped (unknown outcome %r)", outcome)
        return None
    rnd = combat.get("round", 1)
    try:
        chase["rounds"] = int(chase.get("rounds", 0)) + 1
    except (TypeError, ValueError):
        chase["rounds"] = 1
    if outcome == "escape":
        chase["successes"] = int(chase.get("successes", 0)) + 1
    elif outcome == "caught":
        chase["failures"] = int(chase.get("failures", 0)) + 1
    quarry = str(chase.get("quarry", "player"))
    succ, fail = int(chase.get("successes", 0)), int(chase.get("failures", 0))
    target = int(chase.get("target", CHASE_SUCCESSES))
    combat.setdefault("log", []).append({
        "round": rnd, "actor": "system", "name": "",
        "text": (f"chase round {chase['rounds']}: {outcome} "
                 f"(escape {succ}/{target} · catch {fail}/{target})"),
    })
    fx.append({"type": "chase_tick", "value": quarry, "outcome": outcome,
               "successes": succ, "failures": fail, "rounds": chase["rounds"]})
    logger.info("🏃 Chase tick: %s → %s (escape %d/%d · catch %d/%d, round %d)",
                quarry, outcome, succ, target, fail, target, chase["rounds"])
    escaped = caught = False
    escape_cost = 0
    if succ >= target:
        escaped = True
    elif fail >= target:
        caught = True
    elif chase["rounds"] >= CHASE_MAX_ROUNDS:
        # Kapp-lopp (§2.2): avgör på kvarstående klocka — oavgjort = dyr flykt
        if fail > succ:
            caught = True
        else:
            escaped = True
            if fail == succ:
                cur = state.setdefault("currency", {}) if isinstance(state, dict) else {}
                try:
                    gp = int(cur.get("gp", 0))
                except (TypeError, ValueError):
                    gp = 0
                escape_cost = gp // 2
                if escape_cost > 0:
                    cur["gp"] = gp - escape_cost
                fx.append({"type": "chase_escape_cost", "value": escape_cost, "denom": "gp"})
                combat.setdefault("log", []).append({
                    "round": rnd, "actor": "system", "name": "",
                    "text": (f"chase ends at the {CHASE_MAX_ROUNDS}-round cap — the quarry "
                             f"escapes but drops {escape_cost} gp"),
                })
    if not (escaped or caught):
        return chase
    chase["active"] = False
    if escaped:
        chase["result"] = "escaped"
        fx.append({"type": "chase_end", "value": quarry, "result": "escaped"})
        reason = "player fled" if chase.get("mode") == "player_flee" else "enemies fled"
        from guardian import _end_combat  # lazy: undvik import-cirkel
        _end_combat(state, reason, fx,
                    log_text=f"chase: the quarry breaks away and escapes — {reason}")
    else:
        chase["result"] = "caught"
        combat["caught_side"] = "player" if chase.get("mode") == "player_flee" else "enemy"
        fx.append({"type": "chase_end", "value": quarry, "result": "caught"})
        combat.setdefault("log", []).append({
            "round": rnd, "actor": "system", "name": "",
            "text": "chase ends — the quarry is caught! (the pursuer's next attack has advantage)",
        })
    return chase


# ═══════════════════════════════════════
# MORALE (P1a — Moldvay-skalan 2–12)
# ═══════════════════════════════════════

# Trigger-tokener (1.2 i mechanics-p1-flee-morale-spec.md) — dessa sparas i
# morale_checked per fiende och får bara firea EN gång per (fiende, trigger).
MORALE_TRIGGERS = ("first_casualty", "half_down", "leader_down", "fear_effect")
MORALE_STATES = ("steady", "wavering", "broken", "routed")
MORALE_DEFAULT = 8      # genomsnittlig B/X-moral
MORALE_DC = 10          # flat DC — svårigheten ligger i triggerns hårdhet


def ensure_morale(enemy: dict) -> dict:
    """Initiera/sanera moral-fälten på en fiende- eller allierad-entry.

    Tolererar äldre states där fälten saknas (setdefault-semantik, ingen
    KeyError): morale 2–12 (default 8), morale_mod = morale − 7 klampat
    −5..+5, morale_checked = [], morale_state = "steady".
    Returnerar entryn (muterad in place).
    """
    try:
        morale = int(enemy.get("morale", MORALE_DEFAULT))
    except (TypeError, ValueError):
        morale = MORALE_DEFAULT
    morale = max(2, min(12, morale))
    enemy["morale"] = morale
    enemy["morale_mod"] = max(-5, min(5, morale - 7))
    if not isinstance(enemy.get("morale_checked"), list):
        enemy["morale_checked"] = []
    if enemy.get("morale_state") not in MORALE_STATES:
        enemy["morale_state"] = "steady"
    return enemy


def morale_adjustments(state: dict, combat: dict, enemy: dict, trigger: str = "") -> int:
    """Kumulativa moral-modifierare (1.3), klampade −4..+4:

    −2 sidan förlorar hårt (≤50 % av styrkan kvar, spelaren >50 % HP)
    −2 leader_down · −1 fienden under 25 % HP · +1 spelaren synligt sårad (≤50 % HP)
    """
    adj = 0
    enemies = (combat or {}).get("enemies") or []
    initial = max(1, len(enemies))
    alive_count = sum(1 for e in enemies if e.get("alive", True))
    hp = ((state or {}).get("character") or {}).get("hp") or {}
    php, pmax = hp.get("current", 0), hp.get("max", 0) or 0
    if pmax > 0:
        if alive_count * 2 <= initial and php * 2 > pmax:
            adj -= 2
        if php * 2 <= pmax:  # spelaren synligt sårad → de kämpar hårdare
            adj += 1
    if trigger == "leader_down":
        adj -= 2
    ehp, emax = enemy.get("hp", 0), enemy.get("max_hp", 0) or 0
    if emax > 0 and ehp * 4 <= emax:
        adj -= 1
    return max(-4, min(4, adj))


def morale_check(enemy: dict, adjustments: int = 0, rng=None) -> dict:
    """Rent moralprov (P1a) — d20 + morale_mod + adjustments vs DC 10.

    Server-rullad spegel av P0-arkitekturen (enemy_rolls rng-söm): default
    går via modul-globala roll_d20() (testmonkeypatchar combat.roll_d20);
    ett explicit rng-objekt med randbelow() kan skickas in för determinism.

    Utfall (DC = 10): total ≥ 15 → fight_on · 10 ≤ total < 15 → waver ·
    6 ≤ total < 10 → flee · total < 6 → surrender. morale == 12 (fanatiker)
    kollar aldrig → fight_on, skipped=True. adjustments klampas −4..+4.
    """
    try:
        morale = int(enemy.get("morale", MORALE_DEFAULT))
    except (TypeError, ValueError):
        morale = MORALE_DEFAULT
    morale = max(2, min(12, morale))
    morale_mod = max(-5, min(5, morale - 7))
    adj = max(-4, min(4, int(adjustments or 0)))
    bonus = morale_mod + adj
    if morale >= 12:
        return {"d20": 0, "bonus": bonus, "adjustments": adj, "dc": MORALE_DC,
                "total": 0, "outcome": "fight_on", "skipped": True}
    if rng is None:
        d20 = roll_d20()
    else:
        d20 = rng.randbelow(20) + 1
    total = d20 + bonus
    if total >= MORALE_DC + 5:
        outcome = "fight_on"
    elif total >= MORALE_DC:
        outcome = "waver"
    elif total >= MORALE_DC - 4:
        outcome = "flee"
    else:
        outcome = "surrender"
    return {"d20": d20, "bonus": bonus, "adjustments": adj, "dc": MORALE_DC,
            "total": total, "outcome": outcome, "skipped": False}


def _morale_of(e: dict) -> int:
    """Läst moral med default 8 (äldre states utan fältet, §1.1)."""
    try:
        return max(2, min(12, int(e.get("morale", MORALE_DEFAULT))))
    except (TypeError, ValueError):
        return MORALE_DEFAULT


def morale_triggers_for(state: dict, combat: dict) -> list[dict]:
    """Kod-detekterade brytpunkter (§1.2) — rena villkor, ingen side-effekt.

    first_casualty: någon stridande (fiende ELLER allierad) dött — död =
    alive=False utan fled/surrendered (status-skadedöd inkluderat).
    half_down: grupp → alive*2 <= antal; ensam fiende → ≤50 % HP.
    leader_down: ledaren (leader-flagga, annars högst morale) död ELLER flydd.
    fear_effect: ALDRIG automatiskt — bara ansökan via morale_checks/[MORALE:].

    Returnerar [{"target": "all", "trigger": <token>, "note": <str>}, ...].
    """
    enemies = (combat or {}).get("enemies") or []
    if not enemies:
        return []
    out: list[dict] = []

    def _dead(x: dict) -> bool:
        return not x.get("alive", True) and not (x.get("fled") or x.get("surrendered"))

    if any(_dead(x) for x in enemies) or any(_dead(x) for x in ((combat or {}).get("allies") or [])):
        out.append({"target": "all", "trigger": "first_casualty", "note": "auto: first casualty"})
    initial = len(enemies)
    alive_count = sum(1 for e in enemies if e.get("alive", True))
    if initial > 1:
        if alive_count * 2 <= initial:
            out.append({"target": "all", "trigger": "half_down", "note": "auto: half the side is down"})
    else:
        e0 = enemies[0]
        mhp = e0.get("max_hp") or 0
        if e0.get("alive", True) and mhp > 0 and (e0.get("hp") or 0) * 2 <= mhp:
            out.append({"target": "all", "trigger": "half_down", "note": "auto: solo enemy below half HP"})
    flagged = [e for e in enemies if e.get("leader")]
    leader = flagged[0] if flagged else max(enemies, key=_morale_of)
    if (not leader.get("alive", True)) or leader.get("fled"):
        out.append({"target": "all", "trigger": "leader_down", "note": "auto: leader is down"})
    return out


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
        entry = {
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
        }
        # P1a: moral-fält per fiende (default 8) + valfri leader-flagga (§1.1).
        entry["morale"] = e.get("morale", MORALE_DEFAULT)
        entry["leader"] = bool(e.get("leader", False))
        enemies.append(ensure_morale(entry))

    combat = {
        "active": True,
        "round": 1,
        "phase": "awaiting_initiative",  # väntar på initiativslag
        "turn_order": [],
        "current_index": 0,
        "enemies": enemies,
        "allies": [],
        "player_actions": {"action": True, "bonus": True, "reaction": True},
        "log": [],
        "started_turn": state.get("meta", {}).get("turn_count", 0),
        "ended_turn": None,
        # P1a: auto-triggers (first_casualty/half_down/leader_down) — på när
        # striden DEKLARERAR moral ('morale'/'leader' i fiende-indata), så
        # äldre strider/fixtures förblir oförändrade och deterministiska.
        "morale_auto": any(isinstance(e, dict) and ("morale" in e or e.get("leader"))
                          for e in enemies_in),
    }
    world["combat"] = combat
    logger.info("⚔️ Combat started: %s", ", ".join(e["name"] for e in enemies))
    return combat


def add_allies(state: dict, allies_in: list[dict]) -> dict:
    """Lägg till allierade NPC:er till en PÅGÅENDE strid.

    Anropas när en [ALLIERAD:]-tagg anländer mitt i striden (DM låter en
    vänlig NPC slåss vid spelarens sida). Normaliserar allierade på samma
    sätt som fiender och ger dem initiativ (1d20 + attack_bonus) i
    turordningen med nyckel "ally-{id}" — så de syns som egna turer.

    allies_in: [{"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 4, "damage_dice": "1d6+2"}]

    Returnerar combat-dict (eller {} om ingen aktiv strid).
    """
    world = state.setdefault("world", {})
    combat = world.get("combat")
    if not combat or not combat.get("active"):
        logger.warning("🤝 [ALLIERAD:] ignored — no active combat")
        return {}

    allies = []
    for i, a in enumerate(allies_in):
        name = (a.get("name") or f"Allierad {i+1}").strip()
        hp = max(1, int(a.get("hp", 7)))
        entry = {
            "id": i,
            "name": name,
            "hp": hp,
            "max_hp": hp,
            "ac": int(a.get("ac", 10)),
            "alive": True,
            "statuses": [],
            "attack_bonus": int(a.get("attack_bonus", 3)),
            "damage_dice": a.get("damage_dice", "1d6+1"),
            "actions_remaining": 1,
        }
        # P1a: samma moral-fält som fiender (symmetri, §1.1).
        entry["morale"] = a.get("morale", MORALE_DEFAULT)
        entry["leader"] = bool(a.get("leader", False))
        allies.append(ensure_morale(entry))

    if not allies:
        return combat

    combat.setdefault("allies", []).extend(allies)

    # Turordning: om den redan finns (pågående strid) ska allierade få egna
    # turer direkt. Slå initiativ (1d20 + attack_bonus, samma mekanik som
    # fiender i roll_initiative) och sortera in dem — utan att flytta
    # current_index till en annan combatant.
    order = combat.get("turn_order")
    if order:
        current_entry = None
        cidx = combat.get("current_index", 0)
        if 0 <= cidx < len(order):
            current_entry = order[cidx]
        for ally in allies:
            ally_init = roll_d20() + ally.get("attack_bonus", 0)
            order.append({
                "key": f"ally-{ally['id']}",
                "name": ally["name"],
                "initiative": ally_init,
                "acted": False,
            })
        order.sort(key=lambda x: x.get("initiative", 0), reverse=True)
        # Synka frontend-formatet (single source: turn_order → initiative)
        _sync_initiative_view(combat)
        if current_entry is not None:
            for idx, entry in enumerate(order):
                if entry is current_entry:
                    combat["current_index"] = idx
                    break

    combat.setdefault("log", []).append({
        "round": combat.get("round", 1), "actor": "system", "name": "",
        "text": ", ".join(a["name"] for a in allies) + " ansluter sig till striden!",
    })
    logger.info("🤝 Allies joined: %s", ", ".join(a["name"] for a in allies))
    return combat


# ═══════════════════════════════════════
# INITIATIV
# ═══════════════════════════════════════

def _sync_initiative_view(combat: dict) -> None:
    """Single source of truth: combat['initiative'] (frontend-format) byggs
    ALLTID ur combat['turn_order'] så de två aldrig kan divergera.
    Anropas efter varje mutation av turn_order (roll_initiative, add_allies).
    """
    combat["initiative"] = [
        {"key": e["key"], "name": e["name"], "value": e["initiative"]}
        for e in combat.get("turn_order", [])
    ]


def roll_initiative(state: dict, player_roll: int | None = None) -> dict:
    """Slå initiativ för alla deltagare. Sortera fallande.

    player_roll: spelarens initiativslag (1d20+mod). Om None, slå automatiskt.
    Returnerar combat-dict med uppdaterad turn_order.
    """
    combat = state.get("world", {}).get("combat")
    if not combat or not combat.get("active"):
        return combat or {}

    char = state.get("character", {})
    pname = char.get("name", "Player")
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

    for ally in combat.get("allies", []):
        if not ally.get("alive", True):
            continue
        # Allierad-initiativ: samma mekanik som fiender
        ally_init = roll_d20() + ally.get("attack_bonus", 0)
        turn_order.append({
            "key": f"ally-{ally['id']}",
            "name": ally["name"],
            "initiative": ally_init,
            "acted": False,
        })

    # Sortera fallande (högst först)
    turn_order.sort(key=lambda x: x.get("initiative", 0), reverse=True)

    combat["turn_order"] = turn_order
    combat["current_index"] = 0
    combat["phase"] = "combat"

    # Synka till frontend-formatet (single source: turn_order → initiative)
    _sync_initiative_view(combat)

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


def _tick_all_statuses(state: dict, combat: dict, rng=None) -> list[dict]:
    """Ticka status-effekter på alla combatants vid rundstart (P1b §3.1.3).

    EN tick per runda — round-scoped guard `_statuses_ticked_round`
    (mekanik-payloader kan bära både combat_round-signal OCH auto-avancering;
    samma runda får aldrig ticka två gånger). Ordning per entitet: sparprov
    först (§3.1.4, slut-av-tur — fiender/allierade rullas server-side via
    rng-sömen [enemy_rolls-mönstret]; spelaren får status_save_request-
    effekter som DM:en/frontenden förvandlar till [KAST: … SPAR DC N]),
    sedan DoT + duration-avdrag (tick_statuses). Returnerar alla effekter.
    """
    fx_all: list[dict] = []
    rnd = combat.get("round", 1)
    if combat.get("_statuses_ticked_round") == rnd:
        return fx_all  # redan tickad denna runda — double-tick-guard
    combat["_statuses_ticked_round"] = rnd

    # Spelaren
    char = state.get("character", {})
    player_entity = {"hp": char.get("hp", {}).get("current", 0), "statuses": char.get("statuses", [])}
    fx_all.extend(roll_status_saves(player_entity, is_player=True, target="player", rng=rng))
    status_fx = tick_statuses(player_entity)
    fx_all.extend(status_fx)
    if status_fx:
        char.setdefault("hp", {})["current"] = player_entity["hp"]
        char["statuses"] = player_entity["statuses"]
        for fx in status_fx:
            if fx["type"] == "status_dmg":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": char.get("name", "Player"),
                    "text": f"takes {fx['amount']} {fx['status']} damage → **{char.get('name', 'Player')} {player_entity['hp']}/{char.get('hp', {}).get('max', '?')} HP**",
                })

    # Fiender
    for enemy in combat.get("enemies", []):
        if not enemy.get("alive", True):
            continue
        _sfx = roll_status_saves(enemy, target=str(enemy.get("name", "?")), rng=rng)
        fx_all.extend(_sfx)
        for f in _sfx:
            if f["type"] == "status_save":
                _res = "breaks free!" if f.get("success") else "still afflicted"
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": enemy.get("name", "?"),
                    "text": f"{f['status']} save vs DC {f['dc']} (🎲 d20={f['d20']}) — {_res}",
                })
        fx = tick_statuses(enemy)
        fx_all.extend(fx)
        for f in fx:
            if f["type"] == "status_dmg":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": enemy["name"],
                    "text": f"takes {f['amount']} {f['status']} damage → **{enemy['name']} {enemy['hp']}/{enemy.get('max_hp', '?')} HP**",
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
                "name": enemy["name"], "text": "falls",
            })

    # Allierade
    for ally in combat.get("allies", []):
        if not ally.get("alive", True):
            continue
        _sfx = roll_status_saves(ally, target=str(ally.get("name", "?")), rng=rng)
        fx_all.extend(_sfx)
        for f in _sfx:
            if f["type"] == "status_save":
                _res = "breaks free!" if f.get("success") else "still afflicted"
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": ally.get("name", "?"),
                    "text": f"{f['status']} save vs DC {f['dc']} (🎲 d20={f['d20']}) — {_res}",
                })
        fx = tick_statuses(ally)
        fx_all.extend(fx)
        for f in fx:
            if f["type"] == "status_dmg":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": ally["name"],
                    "text": f"takes {f['amount']} {f['status']} damage → **{ally['name']} {ally['hp']}/{ally.get('max_hp', '?')} HP**",
                })
            elif f["type"] == "status_end":
                combat.setdefault("log", []).append({
                    "round": combat.get("round", 1), "actor": "system",
                    "name": ally["name"],
                    "text": f"{f['status']} avtar",
                })
        if ally["hp"] <= 0:
            ally["alive"] = False
            combat.setdefault("log", []).append({
                "round": combat.get("round", 1), "actor": "system",
                "name": ally["name"], "text": "falls",
            })

    return fx_all


# ═══════════════════════════════════════
# STRIDSSLUT — hanteras av guardian._apply_mechanics (combat_end), sedan
# dead-code-passet 2026-08-08. Historik: git log -S end_combat.
# ═══════════════════════════════════════


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

    # Allierade (vänliga NPC:er som slåss vid spelarens sida)
    allies = [a for a in combat.get("allies", []) if a.get("alive", True)]
    if allies:
        a_parts = []
        for a in allies:
            status_str = ""
            if a.get("statuses"):
                status_str = " [" + ", ".join(s["name"] for s in a["statuses"]) + "]"
            a_parts.append(f"{a['name']} ({a['hp']}/{a['max_hp']} HP, AC {a['ac']}){status_str}")
        if en:
            lines.append(f"Allies: {', '.join(a_parts)}")
        else:
            lines.append(f"Allierade: {', '.join(a_parts)}")

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
