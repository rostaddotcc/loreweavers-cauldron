"""w2c: tagg-vägars mekanik i main.py — level-up-bonusar, quest-betalning med
dedup, fallback-COMBAT-taggens player_hp, truth-block dödsmedvetenhet, llms.txt.

Rör endast main.py:s publika funktioner + guardian.apply_mechanics (read-only
dedup-verifikation). Ingen riktig data rörs (conftest: turn_ledgers → tmp).
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import unquote

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import guardian  # noqa: E402


# ── 1. [XP:]-taggen ger level-up-bonusar (max HP etc.) ─────────────────────

def test_xp_tag_level_up_raises_max_hp():
    state = {"character": {
        "name": "Test", "class": "fighter", "level": 1,
        "hp": {"current": 10, "max": 10, "temp": 0},
        "abilities": {"CON": {"mod": 1}},
    }, "meta": {}}
    clean, state, effects = main._parse_mechanical_tags(
        "Du segrar! [XP:350] Bra jobbat.", state)
    ch = state["character"]
    assert ch["level"] == 2
    assert ch["xp"]["current"] == 350
    assert ch["xp"]["next_level"] == 900
    # fighter HD 10 → gain = 10//2 + CON(1) = 6 → max 10+6, full HP vid level-up
    assert ch["hp"]["max"] == 16
    assert ch["hp"]["current"] == 16
    assert any(e.get("type") == "level_up" for e in effects)
    assert "[XP:" not in clean


def test_xp_tag_multi_level_applies_bonuses_each_step():
    state = {"character": {
        "class": "wizard", "level": 1,
        "hp": {"current": 6, "max": 6, "temp": 0},
    }, "meta": {}}
    _, state, effects = main._parse_mechanical_tags("[XP:1000]", state)
    ch = state["character"]
    # 1000 XP → level 3 (300, 900); wizard HD 6 → +3 per level → max 12
    assert ch["level"] == 3
    assert ch["hp"]["max"] == 12
    assert sum(1 for e in effects if e.get("type") == "level_up") == 2


# ── 2. [QUEST_SLUTFÖRD:] betalar + dedup mot Guardian ──────────────────────

def _quest_state(xp_r=150, gold_r=25, with_fields=True):
    q = {"id": "q1", "name": "Råttorna i källaren", "status": "aktiv"}
    if with_fields:
        q["xp_reward"] = xp_r
        q["gold_reward"] = gold_r
    return {
        "character": {"class": "rogue", "level": 1,
                      "hp": {"current": 8, "max": 8, "temp": 0}},
        "quests": [q],
        "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
        "meta": {"turn_count": 7},
    }


def test_quest_tag_pays_xp_and_gold():
    state = _quest_state()
    _, state, effects = main._parse_mechanical_tags(
        "Uppdraget är klart! [QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    q = state["quests"][0]
    assert q["status"] == "slutförd"
    assert q["completed_turn"] == 7
    assert state["character"]["xp"]["current"] == 150
    # 25 gp normaliseras till pp+gp (10 gp = 1 pp) — jämför totalt cp-värde
    assert main.currency_to_cp(state["currency"]) == 25 * main.COIN_TO_CP["gp"]
    # Dedup-tuplarna som Guardians _skip_keys läser måste finnas i effects
    assert any(e.get("type") == "xp" and str(e.get("value")) == "150" for e in effects)
    assert any(e.get("type") == "guld" and str(e.get("value")) == "25"
               and e.get("denom") == "gp" for e in effects)


def test_quest_tag_old_quest_without_fields_uses_defaults():
    state = _quest_state(with_fields=False)
    _, state, effects = main._parse_mechanical_tags(
        "[QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    # Default 100 XP / 0 guld (samma som vid quest-skapande)
    assert state["character"]["xp"]["current"] == 100
    assert state["currency"]["gp"] == 0
    assert any(e.get("type") == "xp" and e.get("value") == 100 for e in effects)
    assert not any(e.get("type") == "guld" for e in effects)


def test_quest_tag_then_guardian_no_double_pay():
    """Ordning 1: tagg-vägen betalar → Guardian post-DM får samma completion
    med skip_effects=tagg-effekterna → ingen dubbelbetalning."""
    state = _quest_state()
    _, state, effects = main._parse_mechanical_tags(
        "[QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    xp_after_tag = state["character"]["xp"]["current"]
    cp_after_tag = main.currency_to_cp(state["currency"])
    # Guardian-simulering (post-DM, samma tur) med exakt main.py:s skip_effects
    guardian.apply_mechanics(
        state, {"quests_completed": ["Råttorna i källaren"]},
        skip_effects=effects)
    assert state["character"]["xp"]["current"] == xp_after_tag == 150
    assert main.currency_to_cp(state["currency"]) == cp_after_tag


def test_quest_guardian_then_tag_no_double_pay():
    """Ordning 2: Guardian betalar först → taggen matchar inte längre en
    aktiv quest (status redan 'slutförd') → ingen dubbelbetalning."""
    state = _quest_state()
    guardian.apply_mechanics(
        state, {"quests_completed": ["Råttorna i källaren"]}, skip_effects=[])
    xp_g = state["character"]["xp"]["current"]
    cp_g = main.currency_to_cp(state["currency"])
    assert xp_g == 150 and cp_g == 25 * main.COIN_TO_CP["gp"]
    _, state, effects = main._parse_mechanical_tags(
        "[QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    assert state["character"]["xp"]["current"] == xp_g
    assert main.currency_to_cp(state["currency"]) == cp_g
    assert not any(e.get("type") == "xp" for e in effects)


def test_quest_tag_dedups_against_same_message_xp_tag():
    """[XP:150] + quest xp_reward=150 i SAMMA svar → bara 150 XP totalt."""
    state = _quest_state(xp_r=150, gold_r=0)
    _, state, effects = main._parse_mechanical_tags(
        "[XP:150] Klart! [QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    assert state["character"]["xp"]["current"] == 150


def test_quest_tag_level_up_grants_bonuses():
    state = _quest_state(xp_r=350, gold_r=0)
    _, state, _ = main._parse_mechanical_tags(
        "[QUEST_SLUTFÖRD:Råttorna i källaren]", state)
    ch = state["character"]
    assert ch["level"] == 2
    # rogue HD 8 → +4 → max 8+4=12, full HP
    assert ch["hp"]["max"] == 12 and ch["hp"]["current"] == 12


# ── 3. Fallback-[COMBAT:]-taggen bär player_hp ─────────────────────────────

def test_combat_tag_dirty_fallback_includes_player_hp(monkeypatch):
    state = {
        "character": {"name": "T", "hp": {"current": 7, "max": 12, "temp": 0}},
        "world": {"combat": {"active": True, "enemies": [], "log": []}},
        "meta": {"combat_tag_dirty": True, "turn_count": 3, "last_effects": []},
        "npcs": [],
    }
    appended = []

    async def _fake_extract(*a, **k):
        return {}

    monkeypatch.setattr(main.store, "get", lambda u, c=None: state)
    monkeypatch.setattr(main.store, "save", lambda s: None)
    monkeypatch.setattr(main.store, "load_transcript", lambda s, last_n=8: [])
    monkeypatch.setattr(main.store, "append_message",
                        lambda s, role, text, meta=None: appended.append((role, text)) or s)
    monkeypatch.setattr(main, "guardian_extract_mechanics", _fake_extract)
    monkeypatch.setattr(main, "_log_activity", lambda *a, **k: None)
    monkeypatch.setattr(main, "format_guardian_summary",
                        lambda *a, **k: "")

    asyncio.run(main._guardian_post_dm_locked(
        "tester", "camp1", "DM-svar", "spelarmeddelande", 3, [], skip_effects=[]))

    combat_msgs = [t for r, t in appended if r == "guardian" and "[COMBAT:" in t]
    assert combat_msgs, "fallback-COMBAT-tagg saknas"
    payload = unquote(combat_msgs[0].split("[COMBAT:")[1].rstrip("]"))
    import json as _json
    data = _json.loads(payload)
    assert data.get("player_hp") == {"current": 7, "max": 12}
    # Exakt EN tagg (dedup-säkringen)
    assert combat_msgs[0].count("[COMBAT:") == 1


# ── 4. Truth-block: dödsmedvetenhet ────────────────────────────────────────

def _dying_state(dead=False, hp_cur=0, hp_max=10):
    ds = {"successes": 0, "failures": 3} if dead else {"successes": 1, "failures": 1}
    if dead:
        ds["dead"] = True
    return {
        "character": {"name": "T", "class": "fighter", "level": 2,
                      "hp": {"current": hp_cur, "max": hp_max, "temp": 0},
                      "death_saves": ds},
        "meta": {},
    }


def test_truth_block_dying_sv():
    block = main.truth_block(_dying_state(), language="sv")
    assert "🩸" in block
    assert "DÖENDE" in block
    assert "DÖDSRÄDDNINGAR" in block
    # Dödsraden kommer FÖRE compact_state-innehållet
    assert block.index("DÖENDE") < block.index("HP 0/10")


def test_truth_block_dead_sv():
    block = main.truth_block(_dying_state(dead=True), language="sv")
    assert "ÄR DÖD" in block
    assert "DÖENDE" not in block


def test_truth_block_dying_en():
    block = main.truth_block(_dying_state(), language="en")
    assert "DYING" in block and "DEATH SAVES" in block


def test_truth_block_healthy_no_death_line():
    block = main.truth_block(_dying_state(hp_cur=8), language="sv")
    assert "🩸" not in block
    assert "DÖENDE" not in block and "ÄR DÖD" not in block


def test_truth_block_survives_missing_dicts():
    # Defensiva läsningar: tom state får inte krascha
    block = main.truth_block({"character": {}}, language="sv")
    assert "SANNING" in block


# ── 5. llms.txt: ingen '300 turns'-lögn, '50 fresh turns every day' ────────

def test_llms_txt_no_300_turns_and_daily_wording():
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        r = c.get("/llms.txt")
    assert r.status_code == 200
    body = r.text
    assert "300 turns" not in body
    assert "signup promo" not in body
    assert "50 fresh turns every day" in body
