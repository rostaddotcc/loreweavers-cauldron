"""Mechanics-gap-implementation (2026-08-08).

Täcker P0-1 (skills/proficiency), P0-2 (spell slots spend), P1-4 (class
features vid level-up), P1-5 (inspiration) och P1-6 (conditions tick +
fiende-disadvantage) — se docs/mechanics-gap-analysis-2026-08.md.
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
    """Minimal spelstate."""
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
                "INT": {"score": 10, "mod": 0},
                "WIS": {"score": 10, "mod": 0},
                "CHA": {"score": 10, "mod": 0},
            },
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


# ── P0-2 Spell slots spend ─────────────────────────────────────────────

def test_spell_slots_spend_decrements():
    state = _make_state()
    state["character"]["spell_slots"] = {"current": 3, "max": 3}
    effects = guardian.apply_mechanics(
        state, _mech(spell_slots_spend=[{"name": "Eldklot", "level": 2}]), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 1
    spend = [e for e in effects if e["type"] == "spell_slots_spend"]
    assert len(spend) == 1 and spend[0]["remaining"] == 1


def test_spell_slots_spend_insufficient_blocks_without_crash():
    state = _make_state()
    state["character"]["spell_slots"] = {"current": 1, "max": 3}
    effects = guardian.apply_mechanics(
        state, _mech(spell_slots_spend=[{"name": "Eldklot", "level": 2}]), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 1
    assert any(e["type"] == "spell_slots_blocked" for e in effects)


def test_cantrip_spend_is_free():
    state = _make_state()
    state["character"]["spell_slots"] = {"current": 2, "max": 3}
    guardian.apply_mechanics(
        state, _mech(spell_slots_spend=[{"name": "Eldblixt", "level": 0}]), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 2


def test_spell_slots_missing_slots_dict_safe():
    state = _make_state()  # ingen spell_slots alls
    effects = guardian.apply_mechanics(
        state, _mech(spell_slots_spend=[{"name": "Eldklot", "level": 1}]), skip_effects=[]
    )
    assert any(e["type"] == "spell_slots_blocked" for e in effects)


# ── Long rest restore (fix 2026-08-10: Guardian satte time_passed istället för
#    rest → spell slots återställdes aldrig mekaniskt. Nu fallback på 8h+/hint.) ──

def _caster_state(level=3, slots_current=1, slots_max=2):
    state = _make_state()
    state["character"]["class"] = "Wizard (School of Knowledge)"
    state["character"]["level"] = level
    state["character"]["spell_slots"] = {"current": slots_current, "max": slots_max}
    state["character"]["hp"] = {"current": 5, "max": 14, "temp": 2}
    return state


def test_long_rest_restores_spell_slots_and_hp():
    """Explicit rest:{kind:'long'} ska fylla slots + HP + hit dice."""
    state = _caster_state()
    effects = guardian.apply_mechanics(
        state, _mech(rest={"kind": "long"}), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 2
    assert state["character"]["hp"]["current"] == 14
    assert state["character"]["hp"]["temp"] == 0
    assert any(e["type"] == "hela" for e in effects)


def test_long_rest_fallback_from_time_passed_hours():
    """Guardian satte time_passed 8h+ men glömde rest → ska tolkas som lång vila."""
    state = _caster_state()
    effects = guardian.apply_mechanics(
        state, _mech(time_passed={"hours": 8, "description": "Overnight long rest from night until dawn"}), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 2
    assert state["character"]["hp"]["current"] == 14
    assert any(e["type"] == "hela" for e in effects)


def test_long_rest_fallback_from_description_hint():
    """time_passed med 'long rest' i beskrivningen men 0h → ändå lång vila."""
    state = _caster_state()
    guardian.apply_mechanics(
        state, _mech(time_passed={"hours": 0, "description": "Long rest and recovery"}), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 2


def test_short_rest_does_not_restore_spell_slots():
    """Kort vila ska INTE fylla spell slots — bara HP via hit die."""
    state = _caster_state(slots_current=1)
    guardian.apply_mechanics(
        state, _mech(rest={"kind": "short"}), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 1


def test_time_passed_short_does_not_trigger_long_rest_fallback():
    """time_passed 2h utan vil-hint → ingen mekanisk återställning."""
    state = _caster_state(slots_current=1)
    guardian.apply_mechanics(
        state, _mech(time_passed={"hours": 2, "description": "Travel through the desert"}), skip_effects=[]
    )
    assert state["character"]["spell_slots"]["current"] == 1


# ── Level-up spell slots + hit dice (fix 2026-08-10) ──

def test_level_up_grows_spell_slots_max_and_hit_dice():
    """Level-up ska öka spell_slots.max enligt 5e-tabellen + hit dice = level."""
    state = _caster_state(level=2, slots_current=3, slots_max=3)
    state["character"]["xp"] = {"current": 900, "next_level": 2700}
    state["character"]["hit_dice"] = {"dice": "1d6", "total": 2, "remaining": 2}
    effects = guardian.apply_mechanics(state, _mech(xp=900), skip_effects=[])
    assert state["character"]["level"] == 3
    assert state["character"]["spell_slots"]["max"] == 4
    assert state["character"]["spell_slots"]["current"] == 4
    assert state["character"]["hit_dice"]["total"] == 3
    assert any(e["type"] == "spell_slots_up" for e in effects)


def test_level_up_non_caster_keeps_no_slots():
    """Icke-kaster ska inte få spell slots vid level-up."""
    state = _make_state()
    state["character"]["class"] = "Fighter"
    state["character"]["level"] = 2
    state["character"]["xp"] = {"current": 900, "next_level": 2700}
    state["character"].pop("spell_slots", None)
    guardian.apply_mechanics(state, _mech(xp=900), skip_effects=[])
    assert state["character"]["level"] == 3
    assert "spell_slots" not in state["character"] or state["character"]["spell_slots"]["max"] == 0


# ── P1-5 Inspiration ───────────────────────────────────────────────────

def test_inspiration_gain_sets_flag():
    state = _make_state()
    effects = guardian.apply_mechanics(state, _mech(inspiration_gain=True), skip_effects=[])
    assert state["character"]["inspiration"] is True
    assert any(e["type"] == "inspiration_gain" for e in effects)


def test_inspiration_spend_clears_flag():
    state = _make_state()
    state["character"]["inspiration"] = True
    effects = guardian.apply_mechanics(state, _mech(inspiration_spend=True), skip_effects=[])
    assert state["character"]["inspiration"] is False
    assert any(e["type"] == "inspiration_spend" for e in effects)


def test_inspiration_spend_without_flag_is_noop():
    state = _make_state()
    effects = guardian.apply_mechanics(state, _mech(inspiration_spend=True), skip_effects=[])
    assert not any(e["type"] == "inspiration_spend" for e in effects)


def test_sanitize_inspiration_string_values():
    mech = {"inspiration_gain": "true", "inspiration_spend": "yes"}
    guardian._sanitize_mechanics(mech)
    assert mech["inspiration_gain"] is True
    assert mech["inspiration_spend"] is True


# ── P0-1 Skills / proficiency ──────────────────────────────────────────

def test_ensure_skills_fills_18():
    ch = {}
    skills = guardian._ensure_skills(ch)
    assert len(skills) == 18
    assert all(s["proficient"] is False for s in skills)
    names = {s["name"] for s in skills}
    assert {"Athletics", "Stealth", "Perception", "Persuasion", "Arcana"} <= names


def test_skill_bonus_adds_proficiency_when_proficient():
    ch = {"abilities": {"DEX": {"score": 16, "mod": 3}}, "proficiency": 2}
    skills = guardian._ensure_skills(ch)
    stealth = next(s for s in skills if s["name"] == "Stealth")
    stealth["proficient"] = True
    assert guardian._skill_bonus(ch, stealth) == 5  # 3 + 2
    stealth["proficient"] = False
    assert guardian._skill_bonus(ch, stealth) == 3


def test_char_context_shows_skills_with_bonus():
    state = _make_state()
    ch = state["character"]
    skills = guardian._ensure_skills(ch)
    stealth = next(s for s in skills if s["name"] == "Stealth")
    stealth["proficient"] = True
    ch["skills"] = skills
    ctx = guardian._format_char_context(state, "en")
    assert "Skills:" in ctx
    assert "Stealth" in ctx
    assert "+5" in ctx  # DEX 3 + proficiency 2


def test_pre_prompt_has_proficiency_rule():
    assert "proficiency" in guardian.GUARDIAN_PRE_SYSTEM
    assert "proficiency" in guardian.GUARDIAN_PRE_SYSTEM_EN


# ── P1-4 Class features vid level-up ───────────────────────────────────

def test_level_up_grants_class_features():
    state = _make_state()
    ch = state["character"]
    ch["class"] = "Fighter"
    ch["level"] = 1
    ch["xp"] = {"current": 299, "next_level": 300}
    effects = guardian.apply_mechanics(state, _mech(xp=1), skip_effects=[])
    assert ch["level"] == 2
    names = [f["name"] for f in ch["features"]]
    assert "Action Surge" in names
    assert any(e["type"] == "features_added" for e in effects)


def test_level_up_features_dedup():
    state = _make_state()
    ch = state["character"]
    ch["class"] = "Wizard"
    ch["level"] = 1
    ch["xp"] = {"current": 299, "next_level": 300}
    ch["features"] = [{"name": "Spellcasting", "level": 1, "description": "redan där"}]
    guardian.apply_mechanics(state, _mech(xp=1), skip_effects=[])
    names = [f["name"] for f in ch["features"]]
    assert names.count("Spellcasting") == 1
    assert "Arcane Tradition" in names  # wizard nivå 2


def test_level_up_unknown_class_no_crash():
    state = _make_state()
    ch = state["character"]
    ch["class"] = "Mysterious Stranger"
    ch["level"] = 1
    ch["xp"] = {"current": 299, "next_level": 300}
    effects = guardian.apply_mechanics(state, _mech(xp=1), skip_effects=[])
    assert ch["level"] == 2
    assert ch.get("features", []) == []


def test_class_alias_swedish():
    state = _make_state()
    ch = state["character"]
    ch["class"] = "Krigare"
    ch["level"] = 1
    ch["xp"] = {"current": 299, "next_level": 300}
    guardian.apply_mechanics(state, _mech(xp=1), skip_effects=[])
    names = [f["name"] for f in ch["features"]]
    assert "Action Surge" in names


# ── P1-6 Conditions tick i tag-combat ──────────────────────────────────

def _start_combat(state, enemies):
    return combat.start_combat(state, enemies)


def test_combat_round_ticks_enemy_status_damage():
    state = _make_state()
    c = _start_combat(state, [{"name": "Giftspindel", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    enemy = c["enemies"][0]
    combat.add_status(enemy, "poison", duration=3)  # 2 skada/runda
    assert enemy["hp"] == 7
    guardian.apply_mechanics(state, _mech(combat_round=2), skip_effects=[])
    assert enemy["hp"] == 5
    # status-loggen hamnade i combat.log
    log = " ".join(e.get("text", "") for e in c.get("log", []))
    assert "poison damage" in log


def test_combat_round_ticks_player_status_damage():
    state = _make_state(hp=14)
    _start_combat(state, [{"name": "Goblin", "hp": 5, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    state["character"]["statuses"] = [{"name": "burn", "duration": 2, "dmg_per_turn": 3}]
    guardian.apply_mechanics(state, _mech(combat_round=2), skip_effects=[])
    assert state["character"]["hp"]["current"] == 11  # 14 - 3


def test_combat_round_no_tick_when_same_round():
    state = _make_state(hp=14)
    c = _start_combat(state, [{"name": "Goblin", "hp": 5, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    enemy = c["enemies"][0]
    combat.add_status(enemy, "poison", duration=3)
    guardian.apply_mechanics(state, _mech(combat_round=1), skip_effects=[])  # samma runda → ingen tick
    assert enemy["hp"] == 5


def test_enemy_attack_disadvantage_rolls_worst(monkeypatch):
    state = _make_state(hp=20)
    c = _start_combat(state, [{"name": "Blind Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    enemy = c["enemies"][0]
    combat.add_status(enemy, "blind", duration=2)  # attack_disadvantage → 2d20 sämst
    # Första d20 = 18 (skulle träffa AC 12 med +3), andra = 5 → disadvantage väljer 5 → miss
    _mock_dice(monkeypatch, d20_seq=[18, 5], dmg_seq=[(3, [2])])
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Blind Vakt"}]), skip_effects=[]
    )
    assert not any(e["type"] == "enemy_hit" for e in effects)
    assert state["character"]["hp"]["current"] == 20


def test_enemy_attack_without_disadvantage_hits(monkeypatch):
    state = _make_state(hp=20)
    _start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[18], dmg_seq=[(3, [2])])
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Vakt"}]), skip_effects=[]
    )
    hits = [e for e in effects if e["type"] == "enemy_hit"]
    assert len(hits) == 1
    assert state["character"]["hp"]["current"] == 17  # 20 - 3
