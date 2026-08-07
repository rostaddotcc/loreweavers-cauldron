"""Regression: dubbel-skada-buggen (2026-08-07, turn 140 i admin-kampanjen).

Symptom: spelaren tappade ~15 HP istället för 6 när en fiendetur narrerades.
DM-närrerad skada — [SKADA:]-taggar OCH Guardian-extraherad "damage" — 
applicerades UTÖVER kodens egna tärningsrullningar (d20 + attack_bonus mot
AC + skade-tärning) för samma enemy_attacks.

Design (v26 chat-first): koden rullar auktoritativt. När enemy_attacks finns
och attackeraren matchar en levande fiende i striden, appliceras BARA kodens
skada på spelarens HP; tagg-/extraction-skada för samma attacker ersätts.

Täcker:
  (a) [SKADA:4]/[SKADA:5] + enemy_attacks (kod rullar miss/2/4) → HP tappar
      BARA kodens 6 (aldrig 4+5+2+4=15)
  (b) ren [SKADA:]-fälla utan enemy_attacks appliceras fortfarande
  (c) P0-exakt-match-dedup ([SKADA:4] + extraction damage 4) fungerar fortfarande
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import combat  # noqa: E402
import guardian  # noqa: E402
import main  # noqa: E402


@pytest.fixture(autouse=True)
def _no_disk(tmp_path, monkeypatch):
    """Säkerhet: aldrig röra riktiga backend/data-filer under tester."""
    monkeypatch.setattr(main.store, "save", lambda state: None)
    # Fallback: om något ändå försöker skriva kampanjfiler → tmp_path
    monkeypatch.setattr(main.store, "_state_path", lambda user, cid: tmp_path / f"{user}_{cid}.json")


def _make_state(hp: int = 14) -> dict:
    """Minimal spelstate — Vespera, AC 12, 14 max HP (turn 140-kampanjen)."""
    return {
        "meta": {"turn_count": 140},
        "character": {
            "name": "Vespera",
            "hp": {"current": hp, "max": 14, "temp": 0},
            "ac": 12,
        },
        "npcs": [],
        "world": {},
    }


def _start_combat(state: dict) -> dict:
    """Öppna striden mot Solke Guard + Security Drone (turn 140-fienderna)."""
    return combat.start_combat(state, [
        {"name": "Solke Guard", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6+1"},
        {"name": "Security Drone", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6+1"},
    ])


def _mech(**overrides) -> dict:
    """Minimal mech-dict med alla stridsfält (tomma som default)."""
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


def _mock_dice(monkeypatch, d20_seq, dmg_seq):
    """Styr kodens tärningar: d20 i följd, skade-rullar i följd (1d6+1)."""
    d20_iter = iter(d20_seq)
    dmg_iter = iter(dmg_seq)

    def _roll_d20():
        try:
            return next(d20_iter)
        except StopIteration:
            return 10  # säkerhetsnät: träff utan skada

    def _roll_dice(notation="1d6+1"):
        try:
            return next(dmg_iter)
        except StopIteration:
            return 1, [1]

    monkeypatch.setattr(combat, "roll_d20", _roll_d20)
    monkeypatch.setattr(combat, "roll_dice", _roll_dice)


# ── (a) [SKADA:]-taggar + enemy_attacks → bara kodens skada ────────────────

def test_skada_tags_plus_enemy_attacks_apply_once(monkeypatch):
    """DM-svar med [SKADA:4]/[SKADA:5] OCH enemy_attacks (kod rullar miss/2/4).

    HP får tappa BARA kodens 6 (14 → 8), aldrig 4+5+2+4 = 15 (14 → 0).
    """
    state = _make_state(hp=14)
    _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[4, 17, 9], dmg_seq=[(2, [1]), (4, [3])])

    # DM:n narrerar samma attacker med [SKADA:]-taggar (main.py applicerar dem)
    reply = ("Drönarens klo river dig, 4 skada. Vakten slår dig med batongen, "
             "5 skada. [SKADA:4] [SKADA:5]")
    _, work_state, tag_effects = main._parse_mechanical_tags(reply, state)
    assert work_state["character"]["hp"]["current"] == 5  # 14 - 9 (taggar)

    mech = _mech(enemy_attacks=[
        {"attacker": "Security Drone"},
        {"attacker": "Solke Guard"},
        {"attacker": "Security Drone"},
    ])
    effects = guardian.apply_mechanics(work_state, mech, skip_effects=tag_effects)

    hp = work_state["character"]["hp"]["current"]
    assert hp == 8, f"Förväntade 14-6=8, fick {hp} (dubbel-skada?)"
    # Kodens rullning syns i effekterna (2 träffar), ingen extra skada-effekt
    hits = [e for e in effects if e["type"] == "enemy_hit"]
    assert len(hits) == 2
    assert {h["damage"] for h in hits} == {2, 4}
    assert not any(e["type"] == "skada" for e in effects)


def test_extracted_damage_plus_enemy_attacks_apply_once(monkeypatch):
    """Turn-140-scenariot utan taggar: Guardian extraherade 4+5 damage TILL
    spelaren OCH enemy_attacks. Koden rullar miss/2/4 → bara 6 appliceras."""
    state = _make_state(hp=12)
    _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[4, 17, 9], dmg_seq=[(2, [1]), (4, [3])])

    mech = _mech(
        damage=[
            {"target": "player", "amount": 4, "type": "slashing"},
            {"target": "player", "amount": 5, "type": "bludgeoning"},
        ],
        enemy_attacks=[
            {"attacker": "Security Drone"},
            {"attacker": "Solke Guard"},
            {"attacker": "Security Drone"},
        ],
    )
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])

    hp = state["character"]["hp"]["current"]
    assert hp == 6, f"Förväntade 12-6=6, fick {hp} (12-15=0 var buggen)"
    assert not any(e["type"] == "skada" for e in effects)
    hits = [e for e in effects if e["type"] == "enemy_hit"]
    assert len(hits) == 2
    assert {h["damage"] for h in hits} == {2, 4}


# ── (b) ren [SKADA:]-fälla (inga enemy_attacks) appliceras fortfarande ─────

def test_pure_skada_trap_without_enemy_attacks_still_applies():
    """Fälla/omgivningsskada via [SKADA:]-taggen utan enemy_attacks → appliceras."""
    state = _make_state(hp=14)
    _start_combat(state)  # aktiv strid, men inga enemy_attacks denna tur

    reply = "Spikarna slår igenom sulan — [SKADA:3]"
    _, work_state, tag_effects = main._parse_mechanical_tags(reply, state)
    assert work_state["character"]["hp"]["current"] == 11  # 14 - 3

    effects = guardian.apply_mechanics(work_state, _mech(), skip_effects=tag_effects)
    assert work_state["character"]["hp"]["current"] == 11  # ingen extra skada
    assert not any(e["type"] == "skada" for e in effects)


def test_extracted_trap_damage_without_enemy_attacks_still_applies():
    """Guardian-extraherad fällskada (mech.damage → player) utan enemy_attacks
    appliceras fortfarande (kanalen för äkta icke-stridsskada är intakt)."""
    state = _make_state(hp=14)
    _start_combat(state)

    mech = _mech(damage=[{"target": "player", "amount": 2, "type": "piercing"}])
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])

    assert state["character"]["hp"]["current"] == 12  # 14 - 2
    assert any(e["type"] == "skada" and e["value"] == 2 for e in effects)


# ── (c) P0-exakt-match-dedup fungerar fortfarande ──────────────────────────

def test_p0_exact_match_dedup_still_works():
    """[SKADA:4]-taggen applicerade 4; Guardian-extraherad damage 4 (exakt
    match) får INTE appliceras en andra gång → totalt 4, inte 8."""
    state = _make_state(hp=14)
    _start_combat(state)

    _, work_state, tag_effects = main._parse_mechanical_tags("[SKADA:4]", state)
    assert work_state["character"]["hp"]["current"] == 10  # 14 - 4

    mech = _mech(damage=[{"target": "player", "amount": 4, "type": "slashing"}])
    effects = guardian.apply_mechanics(work_state, mech, skip_effects=tag_effects)

    assert work_state["character"]["hp"]["current"] == 10  # ingen dubbel
    assert not any(e["type"] == "skada" for e in effects)


def test_same_amount_tag_and_code_roll_applies_once(monkeypatch):
    """[SKADA:4] + enemy_attacks där koden rullar 4 → totalt 4, inte 8
    (taggen återställs och kodens träff appliceras en gång)."""
    state = _make_state(hp=14)
    _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(4, [3])])  # träff, 4 skada

    _, work_state, tag_effects = main._parse_mechanical_tags("[SKADA:4]", state)
    assert work_state["character"]["hp"]["current"] == 10  # 14 - 4 (taggen)

    mech = _mech(enemy_attacks=[{"attacker": "Security Drone"}])
    effects = guardian.apply_mechanics(work_state, mech, skip_effects=tag_effects)

    assert work_state["character"]["hp"]["current"] == 10  # 14 - 4: en gång
    hits = [e for e in effects if e["type"] == "enemy_hit"]
    assert len(hits) == 1 and hits[0]["damage"] == 4
