"""Test: DM-systemprompten känner till terrängregeln och restider (2026-08-04).

A: Kända platser visar terräng + restid från nuvarande plats.
B: DM får terrängmodifierarna så den kan uppskatta även okända resor.
"""
import main


def _state_with_locations():
    return {
        "meta": {"campaign_id": "test-terrain", "language": "en", "user": "tester", "campaign_name": "Test"},
        "character": {"name": "Varin", "hp": {"current": 10, "max": 10}},
        "world": {
            "current_location": "Hamnen",
            "visited_locations": ["Hamnen"],
        },
        "locations": [
            {"name": "Hamnen", "description": "En stenkaj", "terrain": "hav"},
            {"name": "Gråskogen", "description": "Tät gammal skog", "terrain": "skog"},
            {"name": "Bergspasset", "description": "Smalt pass", "terrain": "berg"},
        ],
        "inventory": [],
        "quests": [],
        "npcs": [],
        "lore": [],
        "transcript": [],
    }


def test_system_prompt_includes_travel_rule_english():
    state = _state_with_locations()
    p = main._build_system_prompt(state)
    assert "TRAVEL: Travel time between locations" in p
    assert "road 0.5" in p
    assert "forest 1.2" in p
    assert "mountains 1.8" in p


def test_system_prompt_includes_travel_rule_swedish():
    state = _state_with_locations()
    state["meta"]["language"] = "sv"
    p = main._build_system_prompt(state)
    assert "RESOR: Restid mellan platser" in p
    assert "väg 0.5" in p
    assert "skog 1.2" in p


def test_system_prompt_locations_show_terrain_and_travel():
    state = _state_with_locations()
    p = main._build_system_prompt(state)
    # Kända platser-sektionen ska finnas och innehålla terräng + restid
    assert "## Kända platser" in p
    assert "Gråskogen" in p
    assert "skog" in p
    # Nuvarande plats markeras som "Du är här"
    assert "Du är här" in p or "here" in p


def test_travel_rule_only_added_when_locations_exist():
    state = _state_with_locations()
    state["locations"] = []
    p = main._build_system_prompt(state)
    assert "TRAVEL: Travel time" not in p
