"""Conditions in the engine (2026-10-27).

Before this, a blinded or restrained player was narrated as if nothing had
happened: `compact_state` never showed the player's statuses to the DM, and the
only status the roll engine looked at was the ATTACKER's disadvantage. Now:

  * combat.attack_roll_mode() owns the 5e rule, including the cancel rule
    (advantage + disadvantage = a straight d20);
  * enemy_rolls applies it against the player's statuses, so an attack on a
    blinded/restrained/stunned/paralysed/unconscious hero really rolls 2d20;
  * compact_state prints ACTIVE CONDITIONS with the 5e consequence, so the DM
    stops granting straight rolls to a blinded character.

prone is deliberately NOT "attacks against have advantage" — 5e gates that on
being within 5 ft for melee and gives ranged attackers disadvantage, and the
state carries no distance. No bonus beats a wrong bonus.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import combat
from enemy_rolls import roll_enemy_attack


class ScriptedRng:
    """Deterministic rng seam: randbelow drains the given values, then 1."""

    def __init__(self, *vals):
        self.vals = list(vals)
        self.calls = 0

    def randbelow(self, n):
        self.calls += 1
        v = self.vals.pop(0) if self.vals else 1
        return v % n


def _enemy(**kw):
    e = {"name": "Goblin scout", "attack_bonus": 4, "damage_dice": "1d6+2",
         "hp": 7, "max_hp": 7, "ac": 15, "alive": True, "statuses": []}
    e.update(kw)
    return e


def _status(name):
    return {"name": name, "duration": 2, "dmg_per_turn": 0}


# ── the rule itself ────────────────────────────────────────────────────────

def test_blinded_target_gives_the_attacker_advantage():
    assert combat.attack_roll_mode(_enemy(), {"statuses": [_status("blind")]}) == "adv"


def test_restrained_target_gives_the_attacker_advantage():
    assert combat.attack_roll_mode(_enemy(), {"statuses": [_status("restrain")]}) == "adv"


def test_stunned_paralysed_and_unconscious_all_leave_the_target_open():
    for name in ("stun", "paralyze", "unconscious"):
        assert combat.attack_roll_mode(_enemy(), {"statuses": [_status(name)]}) == "adv", name


def test_blinded_attacker_has_disadvantage():
    assert combat.attack_roll_mode(_enemy(statuses=[_status("blind")]), {"statuses": []}) == "dis"


def test_advantage_and_disadvantage_cancel_to_a_straight_roll():
    both = combat.attack_roll_mode(
        _enemy(statuses=[_status("blind")]),
        {"statuses": [_status("blind")]},
    )
    assert both is None


def test_prone_target_gives_no_automatic_advantage():
    # 5e: melee advantage only within 5 ft, ranged disadvantage — no distance
    # in the state, so the engine must not guess.
    assert combat.attack_roll_mode(_enemy(), {"statuses": [_status("prone")]}) is None


def test_prone_attacker_keeps_its_own_disadvantage():
    assert combat.attack_roll_mode(_enemy(statuses=[_status("prone")]), {"statuses": []}) == "dis"


# ── dice: advantage really rolls two and keeps the best ─────────────────────

def test_advantage_rolls_two_dice_and_keeps_the_higher():
    rng = ScriptedRng(17, 4)  # d20 → 18 then 5
    roll = roll_enemy_attack(_enemy(), "goblin#1", 12, rng=rng,
                             player_statuses=[_status("blind")])
    assert roll["advantage"] is True
    assert roll["disadvantage"] is False
    assert roll["d20"] == 18
    assert roll["roll_expr"].startswith("2d20kh1"), roll["roll_expr"]


def test_disadvantage_keeps_the_lower_die():
    rng = ScriptedRng(17, 4)
    roll = roll_enemy_attack(_enemy(statuses=[_status("poison")]), "goblin#1", 12, rng=rng)
    assert roll["disadvantage"] is True
    assert roll["d20"] == 5
    assert roll["roll_expr"].startswith("2d20kl1"), roll["roll_expr"]


def test_cancelled_modes_roll_a_single_die():
    rng = ScriptedRng(17, 4)
    roll = roll_enemy_attack(_enemy(statuses=[_status("poison")]), "goblin#1", 12, rng=rng,
                             player_statuses=[_status("blind")])
    assert roll["advantage"] is False
    assert roll["disadvantage"] is False
    assert roll["d20"] == 18           # a disadvantage roll would have kept the 5
    assert roll["roll_expr"] == "1d20+4"


def test_planned_rolls_carry_the_same_rule_through_plan_and_store():
    from enemy_rolls import plan_and_store
    combat_state = {
        "active": True, "round": 1,
        "enemies": [{"id": "g1", "name": "Goblin", "hp": 7, "max_hp": 7,
                     "ac": 15, "alive": True, "statuses": [],
                     "attack_bonus": 4, "damage_dice": "1d6+1"}],
    }
    meta = {}
    plan = plan_and_store(combat_state, 12, meta, rng=ScriptedRng(17, 4),
                          player_statuses=[_status("restrain")])
    assert plan and plan[0]["advantage"] is True
    stored = meta["enemy_attack_rolls"]["1"]
    assert stored[plan[0]["key"]]["advantage"] is True


# ── the DM's view of the player's own conditions ────────────────────────────

def test_compact_state_prints_active_conditions_with_their_rule():
    from main import compact_state
    state = {
        "character": {
            "name": "Pemba", "class": "Ranger", "level": 4,
            "hp": {"current": 20, "max": 33}, "ac": 15,
            "statuses": [{"name": "blind", "duration": 2, "dmg_per_turn": 0}],
        },
        "world": {}, "inventory": [], "currency": {},
    }
    sv = compact_state(state, "sv")
    en = compact_state(state, "en")
    assert "AKTIVA VILLKOR:" in sv and "blindad" in sv
    assert "ACTIVE CONDITIONS:" in en and "blinded" in en


def test_compact_state_omits_the_line_when_nothing_is_active():
    from main import compact_state
    state = {"character": {"name": "Pemba", "class": "Ranger", "level": 1,
                           "hp": {"current": 9, "max": 9}, "ac": 13},
             "world": {}, "inventory": [], "currency": {}}
    assert "ACTIVE CONDITIONS" not in compact_state(state, "en")
    assert "AKTIVA VILLKOR" not in compact_state(state, "sv")