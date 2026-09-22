"""P0 (2026-09-22): server-authoritative fiendeattacker.

Täcker:
  - enemy_rolls.roll_enemy_attack — rng-söm (träff/miss/krit/fumble), bonus-klamp
  - enemy_rolls.match_enemy_candidates — fuzzy namn-matchning (ordinals, sv-suffix, Name#id)
  - enemy_rolls.plan_enemy_turn — EN planerad attack per levande fiende per runda
  - enemy_rolls.attack_log_row — bevarade sv/en-format (verbatim-mål från forensik 2026-09-22)
  - guardian.apply_mechanics — lagrad MISS → 0 skada (parry), lagrad HIT → klistrad
    skada (LLM-inflation klotter aldrig igenom), off-list attacker RULLAS (aldrig
    "lita på DM"), multiattack = nytt rull per narrerad attack (turn-140-
    kontraktet), fuzzy-matchad fiende-matchning.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import combat
import guardian
from enemy_rolls import (
    attack_log_row, attack_bonus_for, match_enemy_candidates,
    plan_enemy_turn, pseudo_enemy, roll_enemy_attack,
)


class ScriptedRng:
    """Deterministisk rng-söm: randbelow(n) lämnar först angivna värden, sedan 1."""

    def __init__(self, *vals):
        self.vals = list(vals)

    def randbelow(self, n):
        v = self.vals.pop(0) if self.vals else 1
        return v % n


def _make_state() -> dict:
    return {
        "meta": {"turn_count": 1},
        "character": {
            "name": "Kael",
            "hp": {"current": 20, "max": 20, "temp": 0},
            "ac": 15,
        },
        "world": {},
    }


def _start_combat(state: dict, enemies=None) -> dict:
    return combat.start_combat(state, enemies or [
        {"name": "Goblin", "hp": 7, "ac": 12, "attack_bonus": 3, "damage_dice": "1d6+1"},
    ])


def _mech(**overrides) -> dict:
    mech = {
        "damage": [], "healing": [], "death": [], "xp": 0,
        "player_attacks": [], "enemy_attacks": [], "combat_events": [],
        "ally_attacks": [], "ally_damage": [],
        "combat_start": None, "combat_round": None,
        "initiative_entries": [], "combat_end": None,
        "roll_grants": [], "corrections": [], "logbook": "",
    }
    mech.update(overrides)
    return mech


def _stored_roll(**over) -> dict:
    r = {
        "key": "Goblin#0", "name": "Goblin", "d20": 18, "bonus": 3, "total": 21,
        "ac": 15, "base_ac": 15, "cover": 0, "hit": True, "crit": False,
        "damage": 5, "damage_type": "piercing", "roll_expr": "1d20+3",
        "damage_dice": "1d6+1", "damage_rolls": [4], "disadvantage": False,
    }
    r.update(over)
    return r


def _dupe_guard_combat() -> dict:
    return {
        "active": True,
        "enemies": [
            {"id": 0, "name": "Guard", "hp": 10, "max_hp": 10, "ac": 14, "alive": True, "statuses": []},
            {"id": 1, "name": "Guard", "hp": 8, "max_hp": 8, "ac": 14, "alive": True, "statuses": []},
            {"id": 2, "name": "Guard", "hp": 6, "max_hp": 6, "ac": 12, "alive": True, "statuses": []},
        ],
    }


# ── roll_enemy_attack (rng-söm) ─────────────────────────────────────────

def test_roll_hit_clamps_bonus_uses_stored_stats():
    rng = ScriptedRng(14, 4)  # d20=15, skadetärning=5 → 5+1
    r = roll_enemy_attack(
        {"name": "Goblin", "attack_bonus": 99, "damage_dice": "1d6+1"},
        "Goblin#0", 15, rng=rng)
    assert r["bonus"] == 7                       # bounded-accuracy-klamp +2..+7
    assert r["d20"] == 15 and r["total"] == 22 and r["hit"] is True
    assert r["damage"] == 6 and r["damage_rolls"] == [5]


def test_roll_fumble_always_misses():
    rng = ScriptedRng(0)  # d20=1
    r = roll_enemy_attack({"name": "Goblin"}, "Goblin#0", 5, rng=rng)
    assert r["d20"] == 1 and r["hit"] is False and r["damage"] == 0


def test_roll_crit_doubles_damage_dice():
    rng = ScriptedRng(19, 0, 1)  # d20=20, två 1d6+1 → (1+1)+(2+1)=5
    r = roll_enemy_attack({"name": "Ogre", "damage_dice": "1d6+1"}, "Ogre#0", 30, rng=rng)
    assert r["crit"] is True and r["hit"] is True
    assert r["damage"] == 5 and r["damage_rolls"] == [1, 2]


def test_roll_miss_never_rolls_damage():
    rng = ScriptedRng(2, 19)  # d20=3 +3 = 6 vs AC 15 → miss
    r = roll_enemy_attack({"name": "Goblin"}, "Goblin#0", 15, rng=rng)
    assert r["hit"] is False and r["damage"] == 0 and r["damage_rolls"] == []
    assert rng.vals == [19]  # skadetärningen rullades ALDRIG


# ── match_enemy_candidates (fuzzy — trigger-buggen) ─────────────────────

def test_match_ordinal_picks_second_duplicate():
    hits = match_enemy_candidates(_dupe_guard_combat(), "the second guard")
    assert len(hits) == 1 and hits[0][0] == 1 and hits[0][1]["id"] == 1


def test_match_key_picks_exact_id():
    hits = match_enemy_candidates(_dupe_guard_combat(), "Guard#2")
    assert [e["id"] for _, e in hits] == [2]


def test_match_swedish_definite_form():
    c = {"active": True, "enemies": [{"id": 0, "name": "Vakt", "alive": True}]}
    assert match_enemy_candidates(c, "vakten")[0][1]["name"] == "Vakt"


def test_match_exact_name_returns_all_duplicates_for_rotation():
    hits = match_enemy_candidates(_dupe_guard_combat(), "Guard")
    assert [i for i, _ in hits] == [0, 1, 2]


# ── plan_enemy_turn (pre-DM-sömmen) ─────────────────────────────────────

def test_plan_one_per_living_enemy_respects_round_acted():
    c = _dupe_guard_combat()
    c["round_acted"] = {"player": True, "enemies": {"Guard#0": True}}
    plan = plan_enemy_turn(c, 15, rng=ScriptedRng(2, 2))
    assert [r["key"] for r in plan] == ["Guard#1", "Guard#2"]


def test_plan_empty_under_full_cover():
    c = _dupe_guard_combat()
    c["player_cover"] = "full"
    assert plan_enemy_turn(c, 15, rng=ScriptedRng()) == []


def test_plan_reuses_stored_rolls_without_reroll():
    c = _dupe_guard_combat()
    stored = {"Guard#0": {"key": "Guard#0", "roll_expr": "1d20+3", "hit": False}}
    plan = plan_enemy_turn(c, 15, rng=ScriptedRng(2, 2), stored=stored)
    assert plan[0]["roll_expr"] == "1d20+3"  # återanvänt — inget omrull


# ── attack_log_row (verbatim-mål, forensik 2026-09-22) ──────────────────

def test_log_row_verbatim_sv_miss():
    roll = {"d20": 14, "bonus": 3, "total": 17, "ac": 19, "base_ac": 19, "cover": 0, "hit": False}
    assert attack_log_row(roll, "sv") == "missar dig (🎲 d20=14+3=17 mot AC 19)"


def test_log_row_fumble_short_forms():
    roll = {"d20": 1, "bonus": 3, "total": 4, "hit": False}
    assert attack_log_row(roll, "sv") == "missar dig (nat 1!)"
    assert attack_log_row(roll, "en") == "misses you (natural 1!)"


def test_log_row_en_hit_with_hp():
    roll = {"d20": 18, "bonus": 3, "total": 21, "ac": 15, "base_ac": 15, "cover": 0,
            "hit": True, "crit": False, "damage_type": "piercing",
            "damage_dice": "1d6+1", "damage_rolls": [6]}
    row = attack_log_row(roll, "en", applied_damage=7,
                         player_name="Aelwen", hp={"current": 5, "max": 12})
    assert row == ("hits you — 7 damage (piercing) "
                   "(🎲 d20=18+3=21 vs AC 15 · 1d6+1: [6]=7) → **Aelwen 5/12 HP**")


# ── apply_mechanics (P0-invarianter) ────────────────────────────────────

def test_stored_miss_blocks_claimed_hit():
    state = _make_state()
    _start_combat(state)
    state["meta"]["enemy_attack_rolls"] = {
        "1": {"Goblin#0": _stored_roll(hit=False, damage=0, damage_rolls=[])}}
    mech = _mech(enemy_attacks=[
        {"attacker": "Goblin", "hit": True, "damage": 7, "damage_type": "piercing"}])
    effects = guardian.apply_mechanics(state, mech)
    assert state["character"]["hp"]["current"] == 20          # 0 skada
    assert any(e.get("type") == "enemy_miss" for e in effects)
    log = state["world"]["combat"]["log"]
    assert any("MISS" in r["text"] and "parried" in r["text"] for r in log)


def test_stored_hit_clamps_llm_inflation():
    state = _make_state()
    _start_combat(state)
    state["meta"]["enemy_attack_rolls"] = {"1": {"Goblin#0": _stored_roll()}}  # lagrad skada 5
    mech = _mech(enemy_attacks=[
        {"attacker": "Goblin", "hit": True, "damage": 99, "damage_type": "piercing"}])
    guardian.apply_mechanics(state, mech)
    assert state["character"]["hp"]["current"] == 15          # 20 − 5 (INTE −99)


def test_same_enemy_twice_is_multiattack_not_claims(monkeypatch):
    """Samma fiende två gånger i en tur = MULTIATTACK (turn-140-kontraktet):
    varje entry rullas separat, men skadan är alltid den RULLADE — aldrig
    LLM:ens anspråk (5+5). Extra attacken rullar nytt men pillar inte på
    round_acted-markeringen."""
    state = _make_state()
    _start_combat(state)
    state["meta"]["enemy_attack_rolls"] = {"1": {"Goblin#0": _stored_roll()}}
    d20_iter = iter([17])
    dmg_iter = iter([(2, [1])])
    monkeypatch.setattr(combat, "roll_d20", lambda: next(d20_iter, 10))
    monkeypatch.setattr(combat, "roll_dice", lambda notation="1d6+1": next(dmg_iter, (1, [1])))
    mech = _mech(enemy_attacks=[
        {"attacker": "Goblin", "hit": True, "damage": 5},
        {"attacker": "Goblin", "hit": True, "damage": 5},
    ])
    effects = guardian.apply_mechanics(state, mech)
    # 1:a = lagrad träff (5 rullat) · 2:a = multiattack-edge: d20=17 → +3 = 20
    # vs AC 15 → träff, skada 2 (rullat). ALDRIG 5+5=10 från anspråken.
    assert state["character"]["hp"]["current"] == 13   # 20 − 5 − 2
    hits = [e for e in effects if e.get("type") == "enemy_hit"]
    assert len(hits) == 2 and sorted(h["damage"] for h in hits) == [2, 5]
    c = state["world"]["combat"]
    assert c.get("round_acted", {}).get("enemies", {}).get("Goblin#0")


def test_off_list_attacker_rolls_never_trusts_claims(monkeypatch):
    state = _make_state()
    _start_combat(state)
    monkeypatch.setattr(combat, "roll_d20", lambda: 2)  # d20=2 +3 = 5 vs AC 15 → miss
    mech = _mech(enemy_attacks=[
        {"attacker": "Shadowy stranger", "hit": True, "damage": 50}])
    effects = guardian.apply_mechanics(state, mech)
    assert state["character"]["hp"]["current"] == 20          # 0 skada — aldrig "lita på DM"
    assert any(e.get("type") == "enemy_miss" for e in effects)


def test_apply_fuzzy_match_uses_matched_enemy_stored_roll():
    """Regression: "vakten" måste matcha "Vakt" och använda dess LAGRADA utfall
    (utan fuzzy-matchning hamnar attacken i off-list-vägen med pseudo-stats)."""
    state = _make_state()
    _start_combat(state, [
        {"name": "Vakt", "hp": 10, "ac": 12, "attack_bonus": 3, "damage_dice": "1d6+1"}])
    state["meta"]["enemy_attack_rolls"] = {
        "1": {"Vakt#0": _stored_roll(key="Vakt#0", name="Vakt")}}
    mech = _mech(enemy_attacks=[
        {"attacker": "vakten", "hit": True, "damage": 5, "damage_type": "piercing"}])
    guardian.apply_mechanics(state, mech)
    assert state["character"]["hp"]["current"] == 15          # lagrad skada 5 applicerad
