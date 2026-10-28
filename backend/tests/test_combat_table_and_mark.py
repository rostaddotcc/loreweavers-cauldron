"""Tester för v1.9-vågen 2: stridsstädning, table-rad och Hunter's Mark.

Alla tre kommer ur samma spelarrapport (hero2 2026-10-23): "whether an
enemy is dead", "tends to describe the situation very poetically, rather than
giving an overview", "with tracking spells, spell slots etc its having a hard
time".
"""
import copy

import pytest

import combat
import guardian


def _state(combat_active=True):
    return {
        "character": {
            "name": "Pemba", "class": "ranger", "level": 2, "ac": 15,
            "hp": {"current": 19, "max": 19},
            "features": [{"name": "Sharpshooter"}],
            "spells": [{"name": "Hunter's Mark", "level": 1}],
            "spell_slots": {"current": 2, "max": 2},
        },
        "inventory": [{"name": "Yew Longbow", "damage_dice": "1d8",
                       "equipped": True, "usage": "wielded", "magic_bonus": 0}],
        "npcs": [], "currency": {}, "quests": [],
        "meta": {"turn_count": 10},
        "world": {"combat": {
            "active": combat_active, "round": 2, "phase": "active", "turn_order": [],
            "current_index": 0, "player_actions": {"action": True, "bonus": True, "reaction": True},
            "enemies": [
                {"id": 0, "name": "Tally-Keeper", "hp": 11, "max_hp": 11, "ac": 13, "alive": True, "statuses": []},
                {"id": 1, "name": "False-Pemba", "hp": 2, "max_hp": 11, "ac": 13, "alive": False, "statuses": []},
            ],
            "allies": [], "log": [],
        }},
    }


@pytest.fixture
def fixed_dice(monkeypatch):
    monkeypatch.setattr(combat, "roll_dice", lambda notation: (3, [3]))


# ── 1. Stridsstädning ──────────────────────────────────────────────────

def test_dead_enemy_is_zeroed():
    st = _state()
    combat_block = st["world"]["combat"]
    assert guardian._normalize_combat_deaths(combat_block) == 1
    assert combat_block["enemies"][1]["hp"] == 0
    assert combat_block["enemies"][1]["alive"] is False
    assert combat_block["enemies"][0]["hp"] == 11       # levande orörd
    assert guardian._normalize_combat_deaths(combat_block) == 0   # idempotent


def test_dead_ally_is_zeroed():
    st = _state()
    st["world"]["combat"]["allies"] = [{"name": "Branneth", "hp": 3, "max_hp": 12, "alive": False}]
    guardian._normalize_combat_deaths(st["world"]["combat"])
    assert st["world"]["combat"]["allies"][0]["hp"] == 0


def test_end_combat_zeroes_dead_on_default_path():
    """combat_end utan falls_cleanup ska ändå nolla stupade fiender."""
    st = _state()
    st["world"]["combat"]["enemies"][0]["alive"] = False   # död men hp 11
    effects = []
    ended = guardian._end_combat(st, "all defeated", effects)
    assert ended is True
    assert st["world"]["combat"]["active"] is False
    assert st["world"]["combat"]["enemies"][0]["hp"] == 0


# ── 2. Table-rad ───────────────────────────────────────────────────────

def test_table_line_in_combat_lists_everything():
    st = _state()
    line = guardian.format_table_line(st, "en")
    assert line.startswith("📋 **Table:**")
    assert "Round 2" in line
    assert "19/19 HP" in line and "AC 15" in line
    assert "slots 2/2" in line
    assert "Tally-Keeper 11/11" in line
    assert "down: False-Pemba" in line            # död fiende syns som nere
    assert "2/11" not in line                      # aldrig "död med HP kvar"


def test_table_line_silent_out_of_combat():
    st = _state(combat_active=False)
    assert guardian.format_table_line(st, "en") == ""


def test_table_line_shown_when_a_slot_was_spent():
    st = _state(combat_active=False)
    line = guardian.format_table_line(st, "en", effects=[{"type": "spell_slots_spend", "level": 1}])
    assert "slots 2/2" in line and "Round" not in line


def test_table_line_shows_concentration():
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    assert "mark: Hunter's Mark → Tally-Keeper" in guardian.format_table_line(st, "en")


def test_table_line_swedish_labels():
    st = _state()
    line = guardian.format_table_line(st, "sv")
    assert "Bordet" in line and "Runda 2" in line and "fiender:" in line


# ── 3. Hunter's Mark ───────────────────────────────────────────────────

def test_mark_adds_1d6_on_marked_target(fixed_dice):
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    guardian.apply_mechanics(st, {"player_attacks": [
        {"target": "Tally-Keeper", "hit": True, "damage": 99}]})
    enemy = st["world"]["combat"]["enemies"][0]
    # 1d8=3 (vapen) + 1d6=3 (märket) = 6 — LLM:ens 99 ignoreras
    assert enemy["hp"] == 5


def test_mark_gives_nothing_on_other_target(fixed_dice):
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    st["world"]["combat"]["enemies"][1]["alive"] = True     # andra målet lever
    st["world"]["combat"]["enemies"][1]["hp"] = 11
    guardian.apply_mechanics(st, {"player_attacks": [
        {"target": "False-Pemba", "hit": True, "damage": 99}]})
    enemy = st["world"]["combat"]["enemies"][1]
    assert enemy["hp"] == 11 - 3, "bara vapnets 1d8 — inget märke på annat mål"


def test_concentration_is_set_and_cleared():
    st = _state()
    guardian.apply_mechanics(st, {"concentration": {"spell": "Hunter's Mark", "target": "Tally-Keeper"}})
    assert st["character"]["concentration"]["target"] == "Tally-Keeper"
    guardian.apply_mechanics(st, {"concentration": None})
    assert st["character"]["concentration"] is None


def test_missing_concentration_field_keeps_mark():
    """Ett saknat fält får ALDRIG tysta ett aktivt märke."""
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    guardian.apply_mechanics(st, {"damage": []})
    assert st["character"]["concentration"] is not None


def test_concentration_released_when_target_falls():
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    st["world"]["combat"]["enemies"][0]["alive"] = False
    guardian._sync_concentration(st, st["world"]["combat"])
    assert st["character"]["concentration"] is None


def test_concentration_kept_while_target_stands():
    st = _state()
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    guardian._sync_concentration(st, st["world"]["combat"])
    assert st["character"]["concentration"]["target"] == "Tally-Keeper"


def test_long_rest_clears_concentration():
    st = _state(combat_active=False)
    st["character"]["concentration"] = {"spell": "Hunter's Mark", "target": "Tally-Keeper"}
    guardian.apply_mechanics(st, {"rest": {"kind": "long"}})
    assert st["character"]["concentration"] is None
    assert st["character"]["hp"]["current"] == 19

def test_fled_enemy_keeps_its_hit_points():
    """§1.5-kontraktet: en fiende som FLYR lever i fiktionen — HP bevaras.

    Regressionsvakt: städningen får bara nolla de som faktiskt stupade.
    (Fångades av test_morale_p1a::test_flee_application_routing.)
    """
    st = _state()
    fled = st["world"]["combat"]["enemies"][0]
    fled.update({"alive": False, "fled": True, "hp": 9})
    guardian._normalize_combat_deaths(st["world"]["combat"])
    assert fled["hp"] == 9
    line = guardian.format_table_line(st, "en")
    assert "fled: Tally-Keeper" in line and "down: Tally-Keeper" not in line
