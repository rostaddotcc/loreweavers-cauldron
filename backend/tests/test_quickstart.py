"""Quick start (2026-10-27): a prepared hero, no interview, straight into the scene.

Covers the endpoint contract without touching real campaign data: the store is
stubbed, so the assertions are about what the endpoint decides — pregen written
into the campaign, awakening switched off, an in-medias-res opening chosen.
"""

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main


HERO = {
    "id": "sellsword",
    "label": "The Sellsword",
    "blurb": "Heavy armour, a notched longsword and a debt you have not settled.",
    "character": {
        "name": "Halvard Rask",
        "race": "Human",
        "class": "Fighter",
        "level": 1,
        "alignment": "Neutral",
        "background": "Soldier",
        "hp": {"current": 12, "max": 12, "temp": 0},
        "ac": 18,
        "abilities": {"STR": {"score": 16, "mod": 3}, "DEX": {"score": 12, "mod": 1},
                      "CON": {"score": 14, "mod": 2}, "INT": {"score": 10, "mod": 0},
                      "WIS": {"score": 12, "mod": 1}, "CHA": {"score": 8, "mod": -1}},
        "skills": [{"name": "Athletics", "ability": "STR", "proficient": True}],
        "features": [{"name": "Second Wind", "level": 1, "description": "Regain 1d10+1 HP."}],
        "inventory": [{"name": "Longsword", "type": "Vapen", "qty": 1, "weight": 3.0,
                       "lore": "Notched twice at the ford; the man who sold it never said why.",
                       "equipped": True}],
        "gear": "Longsword",
        "story": "A soldier who stopped asking who paid.",
    },
}


def _run(monkeypatch, request):
    state = {"meta": {"campaign_id": "cid-1", "turn_count": 0},
             "character": {}, "inventory": [], "inventory_clean": [],
             "currency": {}, "world": {}, "npcs": [], "quests": []}
    monkeypatch.setattr(main, "_load_pregens", lambda: [HERO])
    monkeypatch.setattr(main, "_get_current_user", lambda token=None: {"sub": "qa", "role": "player"})
    monkeypatch.setattr(main.store, "create",
                        lambda username, name="", language="en": state)
    monkeypatch.setattr(main.store, "save", lambda s: None)
    return asyncio.run(main.create_campaign_quickstart(request, None)), state


def test_quickstart_writes_the_hero_and_skips_the_awakening(monkeypatch):
    res, state = _run(monkeypatch, main.QuickstartRequest(hero="sellsword", language="en"))
    assert res["ok"] is True
    assert res["campaign_id"] == "cid-1"
    assert res["hero"] == "sellsword"
    assert state["character"]["name"] == "Halvard Rask"
    assert state["character"]["class"] == "Fighter"
    # Ingen frågeintervju — scenen öppnas direkt
    assert state["meta"]["awakening"] is False
    assert state["meta"]["opening_key"].startswith("in_"), state["meta"]["opening_key"]
    assert state["meta"]["quickstart"] == "sellsword"


def test_quickstart_unknown_hero_falls_back_to_the_first(monkeypatch):
    res, state = _run(monkeypatch, main.QuickstartRequest(hero="does-not-exist", language="sv"))
    assert res["hero"] == "sellsword"
    assert state["character"]["name"] == "Halvard Rask"


def test_quickstart_refuses_unknown_language(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(main, "_load_pregens", lambda: [HERO])
    monkeypatch.setattr(main, "_get_current_user", lambda token=None: {"sub": "qa"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.create_campaign_quickstart(
            main.QuickstartRequest(hero="sellsword", language="tlh"), None))
    assert exc.value.status_code == 400


def test_quickstart_503_when_no_pregens(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(main, "_load_pregens", lambda: [])
    monkeypatch.setattr(main, "_get_current_user", lambda token=None: {"sub": "qa"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.create_campaign_quickstart(main.QuickstartRequest(), None))
    assert exc.value.status_code == 503