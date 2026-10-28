"""Mechanics P2 (2026-08-08) — resistans, encumbrance, exhaustion, cover, training.

Täcker P2-luckorna från docs/mechanics-gap-analysis-2026-08.md:
resistans/sårbarhet, encumbrance, exhaustion, cover, darkvision (kontext),
downtime/träning. Se /tmp/spec-mechanics-p2-2026-08.md.
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
    monkeypatch.setattr(main.store, "_state_path", lambda user, cid: tmp_path / f"{user}_{cid}.json")


def _make_state(hp: int = 14) -> dict:
    return {
        "meta": {"turn_count": 1},
        "character": {
            "name": "Vespera",
            "class": "Fighter",
            "level": 1,
            "hp": {"current": hp, "max": 14, "temp": 0},
            "ac": 12,
            "proficiency": 2,
            "abilities": {
                "STR": {"score": 10, "mod": 0},
                "DEX": {"score": 16, "mod": 3},
                "CON": {"score": 14, "mod": 2},
            },
            "max_weight_lbs": 150,
            "resistances": [],
            "vulnerabilities": [],
            "immunities": [],
            "exhaustion": 0,
            "training": [],
        },
        "npcs": [],
        "world": {},
    }


def _mech(**overrides) -> dict:
    mech = {
        "damage": [], "healing": [], "death": [], "xp": 0,
        "player_attacks": [], "enemy_attacks": [], "combat_events": [],
        "ally_attacks": [], "ally_damage": [],
        "combat_start": None, "combat_round": None,
        "initiative_entries": [], "combat_end": None,
        "roll_grants": [], "corrections": [], "logbook": "",
        "spell_slots_spend": [], "inspiration_gain": False, "inspiration_spend": False,
        "exhaustion_change": 0, "cover_set": None, "training_update": [],
    }
    mech.update(overrides)
    return mech


def _mock_dice(monkeypatch, d20_seq, dmg_seq):
    d20_iter = iter(d20_seq)
    dmg_iter = iter(dmg_seq)

    def _roll_d20():
        try:
            return next(d20_iter)
        except StopIteration:
            return 10

    def _roll_dice(notation="1d6+1"):
        try:
            return next(dmg_iter)
        except StopIteration:
            return 1, [1]

    monkeypatch.setattr(combat, "roll_d20", _roll_d20)
    monkeypatch.setattr(combat, "roll_dice", _roll_dice)


# ── Resistans / sårbarhet / immunitet ──────────────────────────────────

def test_resistance_halves_mech_damage():
    state = _make_state(hp=14)
    state["character"]["resistances"] = ["fire"]
    effects = guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": 10, "type": "fire"}]), skip_effects=[]
    )
    assert state["character"]["hp"]["current"] == 9  # 14 - 5
    mods = [e for e in effects if e["type"] == "damage_type_mod"]
    assert len(mods) == 1 and mods[0]["mult"] == 0.5


def test_vulnerability_doubles_mech_damage():
    state = _make_state(hp=14)
    state["character"]["vulnerabilities"] = ["cold"]
    guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": 6, "type": "cold"}]), skip_effects=[]
    )
    assert state["character"]["hp"]["current"] == 2  # 14 - 12


def test_immunity_zeroes_mech_damage():
    state = _make_state(hp=14)
    state["character"]["immunities"] = ["poison"]
    effects = guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": 8, "type": "poison"}]), skip_effects=[]
    )
    assert state["character"]["hp"]["current"] == 14
    mods = [e for e in effects if e["type"] == "damage_type_mod"]
    assert mods and mods[0]["mult"] == 0.0


def test_enemy_attack_respects_player_resistance(monkeypatch):
    state = _make_state(hp=14)
    state["character"]["resistances"] = ["slashing"]
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[18], dmg_seq=[(6, [6])])  # träff, 6 skada
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Vakt", "damage_type": "slashing"}]), skip_effects=[]
    )
    # 6 slashing mot slashing-resistance → 3
    assert state["character"]["hp"]["current"] == 11  # 14 - 3
    assert any(e["type"] == "enemy_hit" and e["damage"] == 3 for e in effects)


def test_tick_statuses_respects_resistance():
    enemy = {"name": "Giftorm", "hp": 10, "statuses": [], "resistances": ["poison"]}
    combat.add_status(enemy, "poison", duration=3)
    fx = combat.tick_statuses(enemy)  # poison 2/runda, resistant → 1
    assert enemy["hp"] == 9
    assert any(f["type"] == "status_dmg" and f["amount"] == 1 for f in fx)


# ── Encumbrance ────────────────────────────────────────────────────────

def test_encumbrance_light_emits_effect_once():
    state = _make_state()
    # STR 10 → light > 50 lb, heavy > 100 lb
    state["inventory"] = [{"name": "Börda", "weight": 60, "qty": 1}]
    effects = guardian.apply_mechanics(state, _mech(), skip_effects=[])
    encs = [e for e in effects if e["type"] == "encumbrance"]
    assert len(encs) == 1 and encs[0]["level"] == "light"


def test_encumbrance_no_change_no_duplicate_effect():
    state = _make_state()
    state["character"]["_encumb"] = "light"
    state["inventory"] = [{"name": "Börda", "weight": 60, "qty": 1}]
    effects = guardian.apply_mechanics(state, _mech(), skip_effects=[])
    assert not any(e["type"] == "encumbrance" for e in effects)


def test_encumbrance_char_context_shows_heavy():
    state = _make_state()
    state["character"]["_encumb"] = "heavy"
    ctx = guardian._format_char_context(state, "en")
    assert "Encumbered (heavy)" in ctx


# ── Exhaustion ─────────────────────────────────────────────────────────

def test_exhaustion_gain_and_clamp():
    state = _make_state()
    effects = guardian.apply_mechanics(state, _mech(exhaustion_change=2), skip_effects=[])
    assert state["character"]["exhaustion"] == 2
    assert any(e["type"] == "exhaustion" and e["level"] == 2 for e in effects)


def test_exhaustion_level4_halves_hp_max():
    state = _make_state(hp=14)
    state["character"]["exhaustion"] = 3
    guardian.apply_mechanics(state, _mech(exhaustion_change=1), skip_effects=[])
    hp = state["character"]["hp"]
    assert hp["max"] == 7  # 14 // 2
    assert hp["max_full"] == 14
    assert hp["current"] <= 7


def test_exhaustion_recovery_below_4_restores_hp():
    state = _make_state(hp=14)
    state["character"]["exhaustion"] = 4
    state["character"]["hp"] = {"current": 7, "max": 7, "temp": 0, "max_full": 14}
    guardian.apply_mechanics(state, _mech(exhaustion_change=-1), skip_effects=[])
    hp = state["character"]["hp"]
    assert hp["max"] == 14
    assert "max_full" not in hp


def test_exhaustion_level6_death():
    state = _make_state(hp=14)
    state["character"]["exhaustion"] = 5
    effects = guardian.apply_mechanics(state, _mech(exhaustion_change=1), skip_effects=[])
    assert state["character"]["exhaustion"] == 6
    assert state["character"]["hp"]["current"] == 0
    assert any(e["type"] == "death" for e in effects)


def test_long_rest_reduces_exhaustion():
    state = _make_state()
    state["character"]["exhaustion"] = 2
    guardian.apply_mechanics(state, _mech(rest={"kind": "long"}), skip_effects=[])
    assert state["character"]["exhaustion"] == 1


# ── Cover ──────────────────────────────────────────────────────────────

def test_cover_half_adds_ac_bonus(monkeypatch):
    state = _make_state(hp=20)
    combat.start_combat(state, [{"name": "Skytt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    guardian.apply_mechanics(state, _mech(cover_set={"target": "player", "cover": "half"}), skip_effects=[])
    _mock_dice(monkeypatch, d20_seq=[10], dmg_seq=[(2, [2])])  # 10+3=13 < 12+2 → miss
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Skytt"}]), skip_effects=[]
    )
    assert not any(e["type"] == "enemy_hit" for e in effects)
    assert state["character"]["hp"]["current"] == 20


def test_cover_full_auto_miss(monkeypatch):
    state = _make_state(hp=20)
    combat.start_combat(state, [{"name": "Skytt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    guardian.apply_mechanics(state, _mech(cover_set={"target": "player", "cover": "full"}), skip_effects=[])
    _mock_dice(monkeypatch, d20_seq=[19], dmg_seq=[(5, [5])])  # skulle träffa annars
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Skytt"}]), skip_effects=[]
    )
    assert not any(e["type"] == "enemy_hit" for e in effects)
    assert any(e["type"] == "enemy_miss" and e.get("reason") == "full_cover" for e in effects)


def test_cover_cleared_on_combat_end():
    state = _make_state()
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10}])
    guardian.apply_mechanics(state, _mech(cover_set={"target": "player", "cover": "half"}), skip_effects=[])
    guardian.apply_mechanics(state, _mech(combat_end={"reason": "vakten flyr"}), skip_effects=[])
    assert state["world"]["combat"]["player_cover"] is None


# ── Training / downtime ────────────────────────────────────────────────

def test_training_completion_grants_proficiency():
    state = _make_state()
    ch = state["character"]
    skills = guardian._ensure_skills(ch)
    stealth = next(s for s in skills if s["name"] == "Stealth")
    stealth["proficient"] = False
    ch["skills"] = skills
    effects = guardian.apply_mechanics(
        state, _mech(training_update=[{"name": "Stealth", "days": 10}]), skip_effects=[]
    )
    assert any(e["type"] == "training_complete" and e["skill"] == "Stealth" for e in effects)
    updated = next(s for s in ch["skills"] if s["name"] == "Stealth")
    assert updated["proficient"] is True
    assert ch["training"] == []  # klar → borttagen


def test_training_accumulates_days():
    state = _make_state()
    ch = state["character"]
    ch["skills"] = guardian._ensure_skills(ch)
    guardian.apply_mechanics(state, _mech(training_update=[{"name": "Perception", "days": 4}]), skip_effects=[])
    assert ch["training"][0]["days_spent"] == 4
    guardian.apply_mechanics(state, _mech(training_update=[{"name": "Perception", "days": 3}]), skip_effects=[])
    assert ch["training"][0]["days_spent"] == 7
    assert ch["training"][0]["days_needed"] == 10


def test_training_non_skill_ignored():
    state = _make_state()
    ch = state["character"]
    ch["skills"] = guardian._ensure_skills(ch)
    guardian.apply_mechanics(
        state, _mech(training_update=[{"name": "Drakträning", "days": 5}]), skip_effects=[]
    )
    assert ch.get("training", []) == []


# ── Sanitize ───────────────────────────────────────────────────────────

def test_sanitize_p2_fields():
    mech = {"exhaustion_change": "3", "cover_set": {"target": "player", "cover": "half"}, "training_update": "Stealth"}
    guardian._sanitize_mechanics(mech)
    assert mech["exhaustion_change"] == 3
    assert mech["cover_set"] == {"target": "player", "cover": "half"}
    assert mech["training_update"] == []


def test_sanitize_cover_invalid_values():
    mech = {"cover_set": {"target": "player", "cover": "mega"}}
    guardian._sanitize_mechanics(mech)
    assert mech["cover_set"] is None
