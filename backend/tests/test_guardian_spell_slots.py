"""Tester för Guardian manual-correction spell_slots_set (fix 2026-08-05).

Guardian kunde tidigare påstå "spell slots reloaded" i text men applicerade
inget — spell_slots fanns inte i manual-correction-JSON:en. Nu ska
spell_slots_set = {current, max} uppdatera character.spell_slots på riktigt.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _no_disk_save(monkeypatch):
    """Förhindra att state sparas till riktiga kampanjfiler på disk."""
    monkeypatch.setattr(main.store, "save", lambda state: None)


def _make_state(spell_slots=None):
    return {
        "meta": {"campaign_id": "test", "user": "tester", "turn_count": 1},
        "character": {
            "name": "Test",
            "class": "Warlock",
            "level": 2,
            "hp": {"current": 5, "max": 14, "temp": 0},
            "spell_slots": spell_slots or {"current": 0, "max": 2},
        },
        "inventory": [],
        "npcs": [],
        "quests": [],
        "world": {"day": 3},
    }


def _correction(instruction, state, reply_json):
    """Kör _guardian_manual_correction med en mockad model_call_fn."""
    import json as _json

    async def fake_model_call(messages):
        return _json.dumps(reply_json)

    return _run(main._guardian_manual_correction(
        instruction, state, "tester", fake_model_call, language="sv",
    ))


def test_spell_slots_set_restores_slots_after_long_rest():
    """Long rest via manual correction ska faktiskt fylla slots (current=max)."""
    state = _make_state(spell_slots={"current": 0, "max": 2})
    report = _correction(
        "Long rest completed, restore spell slots.",
        state,
        {
            "hp_set": 14,
            "spell_slots_set": {"current": 2, "max": 2},
            "report": "Long rest completed. HP restored and spell slots reloaded.",
        },
    )
    assert state["character"]["spell_slots"] == {"current": 2, "max": 2}
    assert "Spell slots set to:** 2/2" in report
    assert "HP set to:** 14/14" in report

def test_spell_slots_set_can_change_max_and_current():
    """Level-up: max ökar och current följer med."""
    state = _make_state(spell_slots={"current": 2, "max": 2})
    _correction(
        "Level 3 warlock, now have 2 pact slots still at 2nd level.",
        state,
        {"spell_slots_set": {"current": 2, "max": 2}, "report": "ok"},
    )
    # inga oönskade effekter om inget ändras
    assert state["character"]["spell_slots"] == {"current": 2, "max": 2}


def test_spell_slots_set_defaults_when_missing():
    """Om character saknar spell_slots skapas de (setdefault)."""
    state = {
        "meta": {"campaign_id": "t", "user": "u"},
        "character": {"name": "T", "hp": {"current": 10, "max": 10}},
        "inventory": [],
        "npcs": [],
        "quests": [],
        "world": {},
    }
    _correction(
        "I learn my first spells, give me 2 slots.",
        state,
        {"spell_slots_set": {"current": 2, "max": 2}, "report": "slots set"},
    )
    assert state["character"]["spell_slots"] == {"current": 2, "max": 2}


def test_guardian_correction_system_prompt_mentions_spell_slots_set():
    """Prompten måste berätta för Guardian att fältet finns."""
    assert "spell_slots_set" in main.GUARDIAN_CORRECTION_SYSTEM
    assert "long rest" in main.GUARDIAN_CORRECTION_SYSTEM
