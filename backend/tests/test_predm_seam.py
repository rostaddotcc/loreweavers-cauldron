"""Pre-DM-sömmen (2026-09-22): fiendeattacker rullas och visas för DM:n INNAN
den narrerar.

Täcker:
  - enemy_rolls.plan_and_store — plan+store determinism (rng-söm), lagringsformen
    är EXAKT den guardian._lookup_stored_roll konsumerar
  - idempotence — andra anropet samma runda rullar ALDRIG om (retry-säkert)
  - prompt-blocket (format_planned_outcomes) — utfallen syns i DM-prompten på
    kampanjens språk, blocket är borta utan aktiv strid eller utan okonsumerade
    utfall
  - multiattack (turn-140-kontraktet) — två rull för samma fiende i en runda
    förblir möjliga VIA EDGE PATH: planeringen planerar EN attack per fiende;
    den andra narrerade attacken hittar inget okonsumerat planerat utfall →
    guardian-kanten rullar ett nytt (roll_enemy_attack i apply_mechanics).
    Detta är avsiktligt — pre-DM-sömmen får ALDRIG kapa multiattack.
  - round-trip — lagra via plan_and_store, konsumera via den BEFINTLIGA
    _lookup_stored_roll (guardian.apply_mechanics): lagrad skada vinner över
    LLM-anspråk, utfallet markeras consumed.

LLM-fri (inga nätverksanrop) — rng-söm + monkeypatchade combat-rollningar.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import combat
import guardian
import main
from enemy_rolls import (
    format_planned_outcomes, plan_and_store, unconsumed_planned_rolls,
)


class ScriptedRng:
    """Deterministisk rng-söm: randbelow(n) lämnar först angivna värden, sedan 1."""

    def __init__(self, *vals):
        self.vals = list(vals)

    def randbelow(self, n):
        v = self.vals.pop(0) if self.vals else 1
        return v % n


class ExplodingRng:
    """Söm som kraschar vid varje anrop — bevisar att ingen omrullning sker."""

    def randbelow(self, n):
        raise AssertionError("re-roll attempted on idempotent second call")


def _state(language: str = "sv") -> dict:
    return {
        "meta": {"turn_count": 1, "campaign_id": "test-predm", "language": language,
                 "user": "tester", "campaign_name": "Test"},
        "character": {"name": "Kael", "hp": {"current": 20, "max": 20, "temp": 0}, "ac": 15},
        "world": {},
        "inventory": [], "currency": {}, "npcs": [], "quests": [],
        "lore": [], "locations": [], "transcript": [],
    }


def _start_combat(state: dict) -> dict:
    c = combat.start_combat(state, [
        {"name": "Goblin", "hp": 7, "ac": 12, "attack_bonus": 3,
         "damage_dice": "1d6+1", "damage_type": "piercing"},
    ])
    # Säkerställ fälten roll-motorn läser (start_combat normaliserar inte stats).
    c["enemies"][0].update({"attack_bonus": 3, "damage_dice": "1d6+1",
                            "damage_type": "piercing"})
    return c


def _mech(**overrides) -> dict:
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


# ── plan_and_store (plan + lagring, rng-söm) ────────────────────────────

def test_plan_store_deterministic_shape_matches_lookup_contract():
    state = _state()
    c = _start_combat(state)
    planned = plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))
    assert [r["key"] for r in planned] == ["Goblin#0"]
    round_map = state["meta"]["enemy_attack_rolls"][str(c.get("round", 1))]
    r = round_map["Goblin#0"]
    # Fälten guardian._lookup_stored_roll + apply_mechanics läser:
    assert r["roll_expr"] == "1d20+3" and r["d20"] == 14
    assert r["total"] == 17 and r["hit"] is True and r["crit"] is False
    assert r["damage"] == 6 and r["damage_rolls"] == [5]
    assert r["damage_type"] == "piercing"
    assert r["ac"] == 15 and r["base_ac"] == 15 and r["cover"] == 0
    assert not r.get("consumed")


def test_plan_store_idempotent_no_reroll_same_round():
    state = _state()
    c = _start_combat(state)
    first = plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))
    # Retry (t.ex. omkörning av chat-turen): samma runda → ingen ny rullning.
    second = plan_and_store(c, 15, state["meta"], rng=ExplodingRng())
    assert second == first
    assert len(state["meta"]["enemy_attack_rolls"][str(c.get("round", 1))]) == 1


def test_plan_store_empty_without_active_combat():
    state = _state()
    assert plan_and_store(None, 15, state["meta"], rng=ExplodingRng()) == []
    assert plan_and_store({"active": False, "enemies": []}, 15,
                          state["meta"], rng=ExplodingRng()) == []
    assert state["meta"].get("enemy_attack_rolls") in (None, {})


# ── prompt-blocket (format_planned_outcomes → _build_system_prompt) ─────

def test_prompt_block_lists_planned_outcomes_sv():
    state = _state("sv")
    c = _start_combat(state)
    plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))
    p = main._build_system_prompt(state)
    assert "PLANERADE FIENDEATTACKER" in p
    assert "- Goblin#0: 1d20+3 → 17 vs AC 15 — TRÄFF · 6 skada (piercing)" in p
    assert "motsäg dem ALDRIG" in p


def test_prompt_block_english_wording():
    state = _state("en")
    c = _start_combat(state)
    plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))
    p = main._build_system_prompt(state)
    assert "PLANNED ENEMY ATTACKS" in p
    assert "- Goblin#0: 1d20+3 → 17 vs AC 15 — HIT · 6 damage (piercing)" in p
    assert "never contradict them" in p
    assert "PLANERADE FIENDEATTACKER" not in p  # ingen sv-läcka i en-kampanjer


def test_prompt_block_absent_without_combat_or_rolls():
    # Ingen strid → inget block.
    state = _state()
    p = main._build_system_prompt(state)
    assert "PLANERADE FIENDEATTACKER" not in p
    assert "PLANNED ENEMY ATTACKS" not in p
    # Strid men alla planerade utfall konsumerade → inget block.
    state2 = _state()
    c = _start_combat(state2)
    plan_and_store(c, 15, state2["meta"], rng=ScriptedRng(13, 4))
    for round_map in state2["meta"]["enemy_attack_rolls"].values():
        for roll in round_map.values():
            roll["consumed"] = True
    p2 = main._build_system_prompt(state2)
    assert "PLANERADE FIENDEATTACKER" not in p2
    assert unconsumed_planned_rolls(state2["meta"], c) == []


def test_format_helpers_empty_inputs():
    assert format_planned_outcomes([], "sv") == ""
    assert format_planned_outcomes(None, "en") == ""
    assert unconsumed_planned_rolls({}, {}) == []
    assert unconsumed_planned_rolls({"enemy_attack_rolls": "corrupt"}, {}) == []


# ── multiattack (turn-140-kontraktet) ───────────────────────────────────

def test_multiattack_second_roll_via_guardian_edge_path(monkeypatch):
    """Två rull för samma fiende i en runda förblir möjliga (turn-140):
    plan_and_store planerar EN attack per fiende; den andra narrerade attacken
    hittar inget okonsumerat planerat utfall → guardian-kanten (edge path i
    apply_mechanics) rullar ett nytt. Skadan är alltid den RULLADE — aldrig
    LLM:ens anspråk. round_acted markeras bara en gång."""
    state = _state()
    c = _start_combat(state)
    plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))  # planerad träff, 6 skada
    d20_iter = iter([17])            # edge-rull: d20=17 +3 = 20 vs AC 15 → träff
    dmg_iter = iter([(2, [1])])      # edge-skada: 1d6+1 → 2
    monkeypatch.setattr(combat, "roll_d20", lambda: next(d20_iter, 10))
    monkeypatch.setattr(combat, "roll_dice", lambda notation="1d6+1": next(dmg_iter, (1, [1])))
    mech = _mech(enemy_attacks=[
        {"attacker": "Goblin", "hit": True, "damage": 5},
        {"attacker": "Goblin", "hit": True, "damage": 5},
    ])
    effects = guardian.apply_mechanics(state, mech)
    hits = [e for e in effects if e.get("type") == "enemy_hit"]
    assert sorted(h["damage"] for h in hits) == [2, 6]    # planerad 6 + edge 2
    assert state["character"]["hp"]["current"] == 12       # 20 − 6 − 2 (aldrig 5+5)
    assert state["world"]["combat"].get("round_acted", {}).get("enemies", {}).get("Goblin#0")


# ── round-trip: plan_and_store → guardian._lookup_stored_roll ───────────

def test_stored_roll_roundtrip_consumed_by_guardian_lookup():
    """Lagra via den nya pre-DM-vägen, konsumera via den BEFINTLIGA
    _lookup_stored_roll (guardian.apply_mechanics): lagrad skada (6)
    appliceras, LLM:ens anspråk (99) klampas bort, utfallet markeras
    consumed och försvinner ur prompt-blocket."""
    state = _state()
    c = _start_combat(state)
    plan_and_store(c, 15, state["meta"], rng=ScriptedRng(13, 4))
    mech = _mech(enemy_attacks=[
        {"attacker": "Goblin", "hit": True, "damage": 99, "damage_type": "piercing"}])
    guardian.apply_mechanics(state, mech)
    assert state["character"]["hp"]["current"] == 14      # 20 − 6 (lagrat), ej −99
    stored = state["meta"]["enemy_attack_rolls"][str(c.get("round", 1))]["Goblin#0"]
    assert stored.get("consumed") is True
    assert unconsumed_planned_rolls(state["meta"], state["world"]["combat"]) == []
