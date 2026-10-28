"""The real pregen roster (backend/data/pregens/heroes.json) must survive the
same normalisation that char-gen runs. A hand-written hero that crashes
_finalize_character_data would 500 the quick-start endpoint, so this test runs
the actual file, not a fixture.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main

ROSTER = BACKEND_DIR / "pregens" / "heroes.json"


def _roster():
    return json.loads(ROSTER.read_text(encoding="utf-8"))["heroes"]


def test_roster_exists_and_has_three_playable_heroes():
    heroes = _roster()
    assert len(heroes) >= 3, "quick start needs at least three choices"
    for h in heroes:
        assert h.get("id") and h.get("label") and h.get("blurb"), h.get("id")
        assert h.get("character", {}).get("name"), h.get("id")


def test_every_hero_survives_the_char_gen_normaliser():
    for hero in _roster():
        ch = json.loads(json.dumps(hero["character"]))  # deep copy
        assert not isinstance(ch.get("gear"), list), (
            f"{hero['id']}: gear must be a string — items belong in inventory")
        out, inventory, _had = main._finalize_character_data(ch, "en")
        assert out.get("name"), hero["id"]
        assert out.get("class") and out.get("race"), hero["id"]
        assert int((out.get("hp") or {}).get("max") or 0) > 0, hero["id"]
        assert int(out.get("ac") or 0) >= 10, hero["id"]
        assert len(inventory) >= 4, f"{hero['id']}: starting kit looks empty"
        for item in inventory:
            assert item.get("lore"), f"{hero['id']}: item without lore: {item.get('name')}"


def test_ability_modifiers_and_hp_are_arithmetically_consistent():
    for hero in _roster():
        ch = hero["character"]
        for ab, data in (ch.get("abilities") or {}).items():
            assert data["mod"] == (data["score"] - 10) // 2, f"{hero['id']} {ab}"


def test_level_one_heroes_only():
    for hero in _roster():
        assert hero["character"].get("level", 1) == 1, (
            f"{hero['id']}: quick start heroes are level 1 by design")