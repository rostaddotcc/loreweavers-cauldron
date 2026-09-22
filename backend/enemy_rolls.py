"""Enemy attack roll engine — server-authoritative fiendeattacker (P0).

KODEN äger fiendernas tärningskast: d20 + attack_bonus mot spelarens AC
(+täckning), nat 20 = kritisk (dubblerade skadetärningar), nat 1 = fumble
(auto-miss). Disadvantage (status) = 2d20, sämst gäller. Skadan rullas vid
träff och är AUKTORITATIV — DM:ens/LLM:ens skadesiffror appliceras aldrig.

Denna modul centraliserar EXAKT den befintliga rull-matemiken (guardian-kanalen
med 35% ärlig träffprocent) plus:
  - match_enemy_candidates(): fuzzy namn-matchning (normalisering, ordinals
    som "the second guard", "Name#id"-nycklar, svenska bestämda former,
    substring) — trigger-buggen bakom "enemies always hit" var namn-matchning
    som föll igenom till "lita på DM"-fallbacken.
  - attack_log_row(): igenkännbara loggrader (sv/en) i det bevarade formatet
    ("missar dig (🎲 d20=14+3=17 mot AC 19)", "misses you (natural 1!)",
    "träffar dig — 6 skada (piercing) (🎲 … · 1d6+1: [5]=6) → **… HP**").
  - plan_enemy_turn(): rund-planering (EN planerad attack per levande fiende
    per runda, round_acted-bokföringen respekterad) — sömmen för pre-DM-utfall.

Bonus/skada-källa (dokumenterad P0-regel): fiendens LAGRADE `attack_bonus`/
`damage_dice` vinner (klampat till bounded-accuracy-bandet +2..+7); saknas de
(förmodernare [STRID:]-spawn, 42/82 i realdata) används gamla standards
+3 / "1d6+1" — identiskt med den befintliga rull-kanalen.

rng-söm: default anropar combat.roll_d20/roll_dice (secrets-backad,
monkeypatch-vänlig via modul-attribut); injicera ett objekt med randbelow(n)
för deterministiska tester. Varje rullning loggas (ENGLISH) — audit trail.
"""
from __future__ import annotations

import logging
import re
import secrets

logger = logging.getLogger("loreweavers.enemy_rolls")

# Bounded-accuracy-band för attack-bonus.
BONUS_MIN = 2
BONUS_MAX = 7

# Förmodernare fiender (saknar attack_bonus) — gamla standarden i rull-kanalen.
DEFAULT_ATTACK_BONUS = 3
DEFAULT_DAMAGE_DICE = "1d6+1"


def enemy_key(e: dict, idx: int) -> str:
    """Unik nyckel per fiende — NAMN + id (fallback: index).

    Samma format som guardian._enemy_key (som delegerar hit) så
    round_acted-bokföringen delar nycklar med planeringen.
    """
    return f"{e.get('name', '?')}#{e.get('id', idx)}"


# ═══════════════════════════════════════
# RNG-SÖM
# ═══════════════════════════════════════

class _SecretsRng:
    """Default rng-söm: secrets-backad via combat-modulens hjälpfunktioner
    (anropade som modul-attribut så tester kan monkeypatcha combat.roll_d20)."""

    def randbelow(self, n: int) -> int:
        return secrets.randbelow(n)


def _resolve_rng(rng):
    return rng if rng is not None else _SecretsRng()


def _roll_d20(rng) -> int:
    if isinstance(rng, _SecretsRng):
        import combat
        return combat.roll_d20()
    return rng.randbelow(20) + 1


def _roll_notation(notation: str, rng) -> tuple[int, list[int]]:
    """Rulla tärningsnotation via rng-sömen. Returnerar (total, [rolls])."""
    if isinstance(rng, _SecretsRng):
        import combat
        return combat.roll_dice(notation)
    m = re.match(r"^(\d+)d(\d+)([+-]\d+)?$", notation.strip().lower().replace(" ", ""))
    if not m:
        return 0, []
    count, sides, mod = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    rolls = [rng.randbelow(sides) + 1 for _ in range(count)]
    return sum(rolls) + mod, rolls


# ═══════════════════════════════════════
# STATS-UPPSLAG
# ═══════════════════════════════════════

def attack_bonus_for(enemy: dict) -> int:
    """Attack-bonus: lagrat `attack_bonus` vinner, klampat till +2..+7.

    Saknas fältet (förmodernare spawn) → +3 — identiskt med den befintliga
    rull-kanalens default (guardian-ankaret i forensikrapporten).
    """
    raw = enemy.get("attack_bonus")
    try:
        bonus = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_ATTACK_BONUS
    return max(BONUS_MIN, min(BONUS_MAX, bonus))


def damage_notation_for(enemy: dict) -> str:
    """Skadetärning: lagrad `damage_dice` vinner, annars 1d6+1."""
    notation = str(enemy.get("damage_dice") or "").strip()
    return notation or DEFAULT_DAMAGE_DICE


def pseudo_enemy(name: str, attack_bonus=None, damage_dice: str = "") -> dict:
    """Fiendestatistikkälla för attackerare utanför combat-listan —
    heuristiska defaults, rull-vägen är densamma (ingen 'lita på DM')."""
    return {
        "name": str(name or "?"),
        "attack_bonus": attack_bonus,
        "damage_dice": str(damage_dice or "").strip(),
    }


# ═══════════════════════════════════════
# FUZZY NAMN-MATCHNING (P0: trigger-buggen)
# ═══════════════════════════════════════

_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "första": 1, "forsta": 1, "andre": 2, "andra": 2, "tredje": 3,
    "fjärde": 4, "fjarde": 4, "femte": 5, "sjätte": 6, "sjatte": 6,
    "sjunde": 7, "åttonde": 8, "attonde": 8, "nionde": 9, "tionde": 10,
}
_ARTICLES = ("the ", "a ", "an ", "en ", "ett ")
# Svenska bestämda suffix-varianter ("goblinen"→"goblin", "vakten"→"vakt").
_DEF_SUFFIXES = ("arna", "ena", "erna", "en", "et", "na", "erna", "n", "t")


def _norm(s: str) -> str:
    s = str(s or "").casefold()
    s = re.sub(r"[^\w\såäöÅÄÖ]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    for art in _ARTICLES:
        if s.startswith(art) and len(s) > len(art) + 2:
            s = s[len(art):].strip()
    return s


def _variants(s: str) -> set[str]:
    """Normaliserade former + svenska bestämda/obestämda varianter."""
    n = _norm(s)
    out = {n, n.replace("-", " "), n.replace(" ", "")}
    for suf in _DEF_SUFFIXES:
        if len(n) - len(suf) >= 3 and n.endswith(suf):
            out.add(n[: -len(suf)])
    # lägg till suffix den andra strängen kan bära: "vakt" → "vakten"
    if len(n) >= 3:
        out |= {n + sfx for sfx in ("en", "et", "na", "arna", "ena")}
    return {v for v in out if v}


def _names_match(a: str, b: str) -> bool:
    return bool(_variants(a) & _variants(b))


def _parse_ordinal(hint: str) -> tuple[int, str] | None:
    """"the second guard" / "andre vakten" / "guard 2" / "2:a vakt" → (2, base)."""
    h = _norm(hint)
    m = re.match(r"^(\d+)(?::[ae]|:e|\.)?\s+(.+)$", h)
    if m:
        return int(m.group(1)), m.group(2)
    m = re.match(r"^(.+?)\s+(\d+)(?::[ae]|:e|\.)?$", h)
    if m and int(m.group(2)) <= 20:
        return int(m.group(2)), m.group(1)
    words = h.split()
    for i, w in enumerate(words):
        if w in _ORDINAL_WORDS:
            rest = " ".join(words[:i] + words[i + 1:]).strip()
            if rest:
                return _ORDINAL_WORDS[w], rest
    return None


def match_enemy_candidates(combat: dict, hint: str) -> list[tuple[int, dict]]:
    """Levande fiender som hint-strängen kan avse — rangordnade.

    Matchningsregler (i prioritetsordning):
      1. "Name#id"-nyckel (dublettnamn) — id + namn-matchning.
      2. Ordinal-referenser ("the second guard", "andre vakten", "guard 2").
      3. Exakt normaliserad namn-matchning (inkl. svenska bestämda former).
      4. Substring (minst 3 tecken) — "the second guard"-fall, smeknamn.
    Tom hint → [] (anroparen roterar bland ALLA levande fiender).
    Returnerar [(index, enemy)] i combat["enemies"]-ordning.
    """
    enemies = combat.get("enemies") or []
    alive = [(i, e) for i, e in enumerate(enemies) if e.get("alive", True)]
    raw = str(hint or "").strip()
    if not raw or not alive:
        return []

    # 1. Name#id
    if "#" in raw:
        name_part, _, id_part = raw.partition("#")
        if id_part.strip().isdigit():
            want = int(id_part.strip())
            hits = [(i, e) for i, e in alive
                    if int(e.get("id", i)) == want
                    and (not name_part.strip() or _names_match(name_part, e.get("name", "")))]
            if hits:
                return hits

    # 2. Ordinal-referens
    ordi = _parse_ordinal(raw)
    if ordi is not None:
        n, base = ordi
        base_hits = [(i, e) for i, e in alive if _names_match(base, e.get("name", ""))]
        if base_hits:
            return [base_hits[min(n, len(base_hits)) - 1]]

    # 3. Exakt (normaliserat)
    hits = [(i, e) for i, e in alive if _names_match(raw, e.get("name", ""))]
    if hits:
        return hits

    # 4. Substring
    hv = _norm(raw)
    if len(hv) >= 3:
        hits = [(i, e) for i, e in alive
                if any(len(v) >= 3 and (v in hv or hv in v) for v in _variants(e.get("name", "")))]
        if hits:
            return hits
    return []


# ═══════════════════════════════════════
# RULLNING
# ═══════════════════════════════════════

def cover_bonus_for(combat: dict) -> int:
    cover = (combat or {}).get("player_cover")
    return 2 if cover == "half" else 5 if cover == "three_quarters" else 0


def roll_enemy_attack(
    enemy: dict,
    key: str,
    player_ac: int,
    cover_bonus: int = 0,
    rng=None,
    claimed_damage_type: str = "",
) -> dict:
    """Rulla EN fiendeattack mot spelarens AC. Returnerar utfalls-dict.

    Fält: key, name, d20, bonus, total, ac (effektiv), base_ac, cover, hit,
    crit, damage, damage_type, roll_expr, damage_dice, damage_rolls,
    disadvantage. `hit` är auktoritativt — extraherade LLM-anspråk avgör aldrig.
    """
    rng = _resolve_rng(rng)
    name = str(enemy.get("name", "?"))
    bonus = attack_bonus_for(enemy)
    base_ac = int(player_ac)
    cover = int(cover_bonus)
    eff_ac = base_ac + cover

    d20 = _roll_d20(rng)
    disadvantage = False
    try:
        from combat import has_disadvantage
        disadvantage = has_disadvantage(enemy)
    except Exception:
        disadvantage = False
    if disadvantage:
        d20 = min(d20, _roll_d20(rng))

    total = d20 + bonus
    crit = d20 == 20
    fumble = d20 == 1
    hit = crit or (not fumble and total >= eff_ac)

    dmg_notation = damage_notation_for(enemy)
    damage = 0
    damage_rolls: list[int] = []
    if hit:
        damage, damage_rolls = _roll_notation(dmg_notation, rng)
        if crit:
            dmg2, rolls2 = _roll_notation(dmg_notation, rng)
            damage += dmg2
            damage_rolls += rolls2
        damage = max(1, damage)

    roll = {
        "key": key,
        "name": name,
        "d20": d20,
        "bonus": bonus,
        "total": total,
        "ac": eff_ac,
        "base_ac": base_ac,
        "cover": cover,
        "hit": bool(hit),
        "crit": bool(crit),
        "damage": int(damage),
        "damage_type": str(claimed_damage_type or enemy.get("damage_type") or "").strip().lower(),
        "roll_expr": ("2d20kl1" if disadvantage else "1d20") + f"+{bonus}",
        "damage_dice": dmg_notation,
        "damage_rolls": list(damage_rolls),
        "disadvantage": disadvantage,
    }
    logger.info(
        "🎲 Enemy attack roll: %s %s → d20=%d + %d = %d vs AC %d%s → %s%s · %d %s (%s [%s])",
        key, roll["roll_expr"], d20, bonus, total, base_ac,
        f"+{cover}" if cover else "",
        "HIT" if roll["hit"] else "MISS", " (CRIT)" if roll["crit"] else "",
        roll["damage"], roll["damage_type"] or "unknown",
        dmg_notation, ", ".join(str(x) for x in damage_rolls),
    )
    return roll


def plan_enemy_turn(
    combat: dict,
    player_ac: int,
    rng=None,
    stored: dict | None = None,
) -> list[dict]:
    """Planera rundans fiendeattacker — EN planerad attack per levande fiende
    som ännu inte agerat (combat['round_acted']['enemies'] bokföringen).

    stored: valfritt {key: redan-rullat-utfall} — ett utfall planeras EXAKT en
    gång per runda och återanvänds oförändrat (ingen omrullning).
    """
    if not combat or not combat.get("active"):
        return []
    rng = _resolve_rng(rng)
    stored = stored if stored is not None else {}
    ra_enemies = (combat.get("round_acted") or {}).get("enemies") or {}
    if combat.get("player_cover") == "full":
        return []  # full täckning → ingen fiende kan nå spelaren
    cover = cover_bonus_for(combat)

    plan: list[dict] = []
    seen: set[str] = set()
    for i, enemy in enumerate(combat.get("enemies", []) or []):
        if not enemy.get("alive", True):
            continue
        key = enemy_key(enemy, i)
        if key in seen or ra_enemies.get(key):
            continue  # redan agerat/planerat denna runda
        seen.add(key)
        prior = stored.get(key)
        if isinstance(prior, dict) and prior.get("roll_expr"):
            plan.append(prior)  # redan rullat — återanvänd, rulla aldrig om
            continue
        plan.append(roll_enemy_attack(enemy, key, player_ac, cover_bonus=cover, rng=rng))
    return plan


# ═══════════════════════════════════════
# LOGGRADER (bevarat format — sv/en)
# ═══════════════════════════════════════

def _ac_str(roll: dict) -> str:
    """AC-token: effektiv AC; cover specificeras som (bas+bonus) om det finns
    (igenkännbart från realdatans 'vs AC 16+2'-form)."""
    base = roll.get("base_ac", roll.get("ac", 0))
    cover = roll.get("cover", 0)
    eff = roll.get("ac", base)
    try:
        base, cover, eff = int(base), int(cover), int(eff)
    except (TypeError, ValueError):
        base, cover, eff = 0, 0, 0
    if cover:
        return f"{eff} ({base}+{cover})"
    return f"{eff}"


def attack_log_row(
    roll: dict,
    lang: str = "sv",
    applied_damage: int | None = None,
    player_name: str | None = None,
    hp: dict | None = None,
) -> str:
    """Bygg den BEVARADE fiendeattack-raden (sv/en).

    Verbatim-mål (realdata 2026-09-22):
      sv miss : "missar dig (🎲 d20=14+3=17 mot AC 19)"
      sv fum. : "missar dig (nat 1!)"                      ← utan totals
      en fum. : "misses you (natural 1!)"                  ← utan totals
      sv träff: "träffar dig — 6 skada (piercing) (🎲 d20=16+3=19 · 1d6+1: [5]=6)"
      en träff: "hits you — 7 damage (piercing) (🎲 d20=18+3=21 · 1d6+1: [6]=7) → **Namn 5/12 HP**"
      krit    : "… (bludgeoning) 💥 KRITISK! (🎲 …"
    Träffraden bär numera även AC-token (krävs av verifieringsharnessn).
    """
    sv = str(lang or "sv").lower().startswith("sv")
    d20 = int(roll.get("d20", 0))
    bonus = int(roll.get("bonus", 0))
    total = int(roll.get("total", 0))

    # Fumble: utan totals (bevarat kortformat).
    if d20 == 1:
        return "missar dig (nat 1!)" if sv else "misses you (natural 1!)"

    dice = int(roll.get("d20", 0))
    roll_seg = f"🎲 d20={dice}+{bonus}={total}"
    ac_tok = f"{'mot' if sv else 'vs'} AC {_ac_str(roll)}"

    if not roll.get("hit"):
        return f"{'missar dig' if sv else 'misses you'} ({roll_seg} {ac_tok})"

    dtype = str(roll.get("damage_type") or "").strip() or "unknown"
    crit_str = " 💥 KRITISK!" if roll.get("crit") else ""
    head = f"{'träffar dig' if sv else 'hits you'} — {int(applied_damage or 0)} {'skada' if sv else 'damage'} ({dtype}){crit_str}"
    notation = str(roll.get("damage_dice") or DEFAULT_DAMAGE_DICE)
    rolls = ", ".join(str(x) for x in (roll.get("damage_rolls") or []))
    row = f"{head} ({roll_seg} {ac_tok} · {notation}: [{rolls}]={int(applied_damage or 0)})"
    if hp and player_name:
        row += f" → **{player_name} {hp.get('current', '?')}/{hp.get('max', '?')} HP**"
    return row
