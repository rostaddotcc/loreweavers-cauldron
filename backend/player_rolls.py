"""Player attack roll engine — server-authoritative spelarattacker (P0).

Samma filosofi som `enemy_rolls`: KODEN äger tärningarna. Fiendernas attacker
rullas redan pre-DM av enemy_rolls; spelarens attack rullades tidigare EFTER
DM:en (guardian post-DM) — vilket gav tre symptom i produktion:

  1. DM:n narrerade träff/miss innan någon siffra fanns ("the rider's fate
     hangs on the engine's damage roll") och spelaren fick aldrig numret.
  2. DM-prompten förbjuder DM:n att ange vapenskada, medan guardian-prompten
     krävde att DM:n "anger skada" för att extrahera attacken ⇒ attacken
     försvann tyst när DM:n lydde (hero2: 25 av 32 attackturer utan
     HP-ändring).
  3. Träff/miss avgjordes av DM:ens prosa om [Resultat:]-raden, så en
     dubbelpostad rullning (18 sedan 11) kunde bli en miss — spelaren såg
     "rolled an 18, why didnt that hit?".

Denna modul löser 1–3 genom att rulla spelarens attack i PRE-DM-sömmen:

  - `parse_attack_result()` läser [Resultat:]-raden (som redan innehåller
    AC + totalsumma) → träff/miss/krit är ARITMETIK, inte prosa.
  - `plan_player_attack()` rullar vapnets damage_dice (räknar in
    magic_bonus + Sharpshooter +10 när labeln säger SHARPSHOOTER) och
    lagrar planen i `state["meta"]["player_attack_plan"]`.
  - `format_attack_block()` ger DM:n ett AUKTORITATIVT block i prompten —
    DM:n behöver aldrig gissa, och får nu (till skillnad från tidigare)
    numret den ska narrera.
  - `consume_player_attack()` låter guardian post-DM APPLICERA planen i
    stället för att rulla om eller tro på prosan.

Målet väljs INTE här (ingen gissning från regex) — guardian matchar
fiendenamnet i narrationen som förut. Bara träff/miss + skada är förutbestämt,
och de är måloberoende.

Fail-open: kan raden inte tolkas (okänd form, okänt AC, DC-kast) returneras
None och spelet faller tillbaka på det gamla post-DM-flödet. Modulen hittar
aldrig på ett utfall.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("loreweavers.player_rolls")

PLAN_KEY = "player_attack_plan"

# [Resultat: ATTACK vs AC 13 → 18 (12+6)]
# [Resultat: SHARPSHOOTER ATTACK vs Lead Worg Rider AC 13 → 24 (19+5)]
# [Resultat: ATTACK vs AC 13 (Sharpshooter −5/+10) ADVANTAGE → 18 (17, 13+1)]
# [Resultat: Pemba's longbow attack vs Orc (Cover) AC 13 → 14 (8+6)]
_ATTACK_RE = re.compile(r"\battack\b", re.I)
_AC_RE = re.compile(r"\bAC\s*(\d+)\b", re.I)
_TOTAL_RE = re.compile(r"→\s*(\d+)\b")
# Tredjeparts-attacker (allierade/fiender rullade via DM:ens [KAST:]) ska
# ALDRIG bli spelarens attack. Signatur: "vs <namn>" där namnet inte är en
# fiende (Lone Worg bite vs Mara, Jory's slingshot ...).
_VS_RE = re.compile(r"\bvs\.?\s+(?!AC\b)([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?)")
_RESULT_MARK = "[Resultat:"


def _num(val, default=0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def parse_attack_result(text: str) -> dict | None:
    """Tolka en [Resultat:]-rad som en spelarattack.

    Returnerar {"total", "ac", "hit", "crit", "nat"} eller None när raden
    inte är en tolkbar attackrullning (DC-kast, dödsräddning, okänt AC …).
    """
    if not text or _RESULT_MARK not in text:
        return None
    line = text.strip()
    if not _ATTACK_RE.search(line):
        return None
    ac_m = _AC_RE.search(line)
    tot_m = _TOTAL_RE.search(line)
    if not ac_m or not tot_m:
        return None
    ac = _num(ac_m.group(1))
    total = _num(tot_m.group(1))
    if ac <= 0 or total <= 0:
        return None
    # Naturlig tärning ur sista parentesen: "(19+5)" → 19, "(17, 13+1)" → 17.
    # Sista parentesen i raden är alltid tärningsdetaljen (beskrivande
    # parenteser som "(Cover)" står före "AC"-talet).
    nat = None
    paren = re.findall(r"\(([^()]*)\)", line)
    for group in reversed(paren):
        first = group.split(",")[0].strip()
        nat_m = re.match(r"(\d+)\s*([+,]|$)", first)
        if nat_m:
            nat = _num(nat_m.group(1))
            break
    crit = nat == 20
    return {
        "total": total,
        "ac": ac,
        "hit": True if crit else (total >= ac),
        "crit": crit,
        "nat": nat,
    }


def _foreign_roll(line: str, state: dict) -> bool:
    """True om raden rullar någon ANNANS attack (allierad/fiende).

    Endast "vs <namn>" där namnet är en känd icke-fiende räknas — spelarens
    egna attacker skriver aldrig "vs <allierad>".
    """
    m = _VS_RE.search(line)
    if not m:
        return False
    player = _norm((state.get("character") or {}).get("name", ""))
    for m in _VS_RE.finditer(line):
        who = _norm(m.group(1))
        if not who or (player and who in player):
            continue
        for npc in (state.get("npcs") or []):
            if _norm(npc.get("name", "")) == who and npc.get("relation") not in ("fiende", "enemy"):
                return True
    return False


def equipped_weapon(state: dict) -> dict | None:
    """Vapnet som slår — equipped först, annars första wielded med dice."""
    weapons = [
        it for it in (state.get("inventory") or [])
        if str(it.get("damage_dice") or "").strip()
        and not str(it.get("usage") or "").lower() == "consumable"
    ]
    if not weapons:
        return None
    for it in weapons:
        if it.get("equipped"):
            return it
    for it in weapons:
        if str(it.get("usage") or "").lower() == "wielded":
            return it
    return weapons[0]


def _has_feature(state: dict, needle: str) -> bool:
    needle = needle.lower()
    for f in (state.get("character") or {}).get("features") or []:
        name = f.get("name", "") if isinstance(f, dict) else str(f)
        if needle in str(name).lower():
            return True
    return False


def roll_weapon_damage(state: dict, crit: bool = False, label: str = "") -> dict | None:
    """Rulla vapnets skada (+ magic_bonus, + Sharpshooter +10 om labeln säger det)."""
    weapon = equipped_weapon(state)
    if not weapon:
        return None
    notation = str(weapon.get("damage_dice")).strip()
    mb = _num(weapon.get("magic_bonus"), 0)
    if mb:
        notation += ("+%d" % mb if mb > 0 else "%d" % mb)
    try:
        from combat import roll_dice
        total, rolls = roll_dice(notation)
        if crit:
            extra, extra_rolls = roll_dice(notation)
            total += extra
            rolls = list(rolls) + list(extra_rolls)
    except Exception as e:  # tärningsmotor saknas → fail-open
        logger.warning("player_rolls: damage roll failed (%s) — falling back", e)
        return None
    bonus = 0
    notes = []
    if "sharpshooter" in label.lower() and _has_feature(state, "sharpshooter"):
        bonus += 10
        notes.append("Sharpshooter +10")
    return {
        "notation": notation,
        "rolls": list(rolls),
        "damage": total + bonus,
        "bonus": bonus,
        "notes": notes,
        "weapon": weapon.get("name"),
        "crit": bool(crit),
    }


def plan_player_attack(state: dict, player_input: str) -> dict | None:
    """Pre-DM-söm: planera spelarens attack. Idempotent per meddelande.

    Lagrar/rensar `meta[PLAN_KEY]`. Anropas varje tur, precis före DM-prompten.
    """
    meta = state.setdefault("meta", {})
    line = (player_input or "").strip()
    if _RESULT_MARK not in line:
        meta.pop(PLAN_KEY, None)
        return None
    combat = (state.get("world") or {}).get("combat") or {}
    if not combat.get("active"):
        meta.pop(PLAN_KEY, None)
        return None
    if _foreign_roll(line, state):
        meta.pop(PLAN_KEY, None)
        logger.info("player_rolls: third-party attack roll → not a player attack")
        return None
    parsed = parse_attack_result(line)
    if parsed is None:
        meta.pop(PLAN_KEY, None)
        return None
    existing = meta.get(PLAN_KEY)
    if isinstance(existing, dict) and existing.get("msg") == line[:200]:
        return existing
    dmg = roll_weapon_damage(state, crit=parsed["crit"], label=line)
    if dmg is None:
        meta.pop(PLAN_KEY, None)
        return None
    plan = dict(parsed)
    plan.update(dmg)
    plan["msg"] = line[:200]
    meta[PLAN_KEY] = plan
    if parsed["hit"]:
        logger.info(
            "🎲 Player attack planned (pre-DM): %d vs AC %d → HIT · %d damage (%s%s)",
            parsed["total"], parsed["ac"], plan["damage"], plan["notation"],
            (" · " + ", ".join(plan["notes"])) if plan["notes"] else "",
        )
    else:
        logger.info("🎲 Player attack planned (pre-DM): %d vs AC %d → MISS",
                    parsed["total"], parsed["ac"])
    return plan


def consume_player_attack(state: dict, player_msg: str | None = None) -> dict | None:
    """Hämta (och förbruka) planen när guardian post-DM applicerar attacken."""
    meta = state.setdefault("meta", {})
    plan = meta.get(PLAN_KEY)
    if not isinstance(plan, dict):
        return None
    if player_msg is not None and plan.get("msg") and plan.get("msg") != (player_msg or "").strip()[:200]:
        return None
    meta.pop(PLAN_KEY, None)
    return plan


def format_attack_block(plan: dict, lang: str = "sv") -> str:
    """Auktoritativt DM-promptblock: utfallet är redan rullat."""
    verdict = "MISS" if not plan.get("hit") else ("CRITICAL HIT" if plan.get("crit") else "HIT")
    line = "**%s — %d vs AC %d**" % (verdict, plan.get("total", 0), plan.get("ac", 0))
    dmg_bit = ""
    if plan.get("hit"):
        dmg_bit = " · **%d damage** (%s%s%s)" % (
            plan.get("damage", 0), plan.get("notation", "?"),
            " ×2 crit" if plan.get("crit") else "",
            (" · " + ", ".join(plan.get("notes") or [])) if plan.get("notes") else "",
        )
    if lang == "sv":
        return (
            "\n## 🎲 SPELARENS ATTACK — REDAN RULLAD AV MOTORN\n"
            f"{line}{dmg_bit}\n"
            "Detta är ARITMETIK, inte prosa: träff/miss och skadan är avgjorda.\n"
            "1. Narrera EXAKT detta utfall — aldrig en miss om raden säger HIT.\n"
            "2. Skadan ovan är den enda giltiga siffran; hitta inte på en egen.\n"
            "3. Ange vilken fiende attacken träffar (namnet ur stridstillståndet).\n"
            "4. Motorn lägger fiendens nya HP i stridsloggen — skriv inga HP-tal själv."
        )
    return (
        "\n## 🎲 PLAYER ATTACK — ALREADY ROLLED BY THE ENGINE\n"
        f"{line}{dmg_bit}\n"
        "This is ARITHMETIC, not prose: hit/miss and the damage are settled.\n"
        "1. Narrate EXACTLY this outcome — never a miss when the line says HIT.\n"
        "2. The damage above is the only valid number; do not invent your own.\n"
        "3. State which enemy the attack strikes (name it from the combat state).\n"
        "4. The engine appends the enemy's new HP to the combat log — do not state HP numbers yourself."
    )