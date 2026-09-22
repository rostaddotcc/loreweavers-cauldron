"""P1a-smoketester: moral + routning (LLM-fria).

Direkta anrop till combat.morale_check / guardian.apply_mechanics med
handskrivna mech-dicts — ingen nätverk, ingen LLM. Fixtures med DUBLETTNAMN
(3× 'Guard') för Name#id-rotationen. Rull determiniseras genom rng-sömen
(monkeypatch av combat.roll_d20 — samma mönster som P0-testerna).
"""
import pytest

import combat as combat_mod
import guardian


# ─────────────────────────────────────────────────────────────
# Hjälpare
# ─────────────────────────────────────────────────────────────

def force_rolls(monkeypatch, values):
    """Deterministiska d20-rull via rng-sömen (P0-mönstret)."""
    it = iter(values)
    monkeypatch.setattr(combat_mod, "roll_d20", lambda: next(it))


def make_state(enemy_specs, *, player_hp=(20, 20)):
    """State + combat via combat.start_combat (rätt id/Name#id-nycklar)."""
    state = {
        "meta": {"turn_count": 3},
        "character": {
            "name": "Testhjälte",
            "hp": {"current": player_hp[0], "max": player_hp[1], "temp": 0},
        },
    }
    combat_mod.start_combat(state, [dict(e) for e in enemy_specs])
    return state


def morale_effects(effects):
    return [e for e in effects if e.get("type") == "morale_check"]


GUARD3 = [
    {"name": "Guard", "hp": 10, "ac": 14, "morale": 6},
    {"name": "Guard", "hp": 10, "ac": 14, "morale": 8},
    {"name": "Guard", "hp": 10, "ac": 14, "morale": 7},
]


# ─────────────────────────────────────────────────────────────
# 1. morale_check — rena utfallsband + modifierare
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("d20,expected", [
    (20, "fight_on"),   # total 21 ≥ 15
    (11, "waver"),      # total 12 ∈ [10, 15)
    (7, "flee"),        # total 8 ∈ [6, 10)
    (1, "surrender"),   # total 2 < 6
])
def test_morale_check_outcome_bands(monkeypatch, d20, expected):
    force_rolls(monkeypatch, [d20])
    enemy = {"name": "Goblin", "morale": 8}  # mod +1
    roll = combat_mod.morale_check(enemy)
    assert roll["outcome"] == expected
    assert roll["d20"] == d20
    assert roll["bonus"] == 1
    assert roll["dc"] == 10
    assert roll["total"] == d20 + 1
    assert roll["skipped"] is False


def test_morale_check_morale_12_never_checks():
    roll = combat_mod.morale_check({"name": "Fanatiker", "morale": 12})
    assert roll["outcome"] == "fight_on"
    assert roll["skipped"] is True


def test_morale_check_adjustments_clamped():
    # adjustments klampas −4..+4 oavsett indata (§1.3)
    hi = combat_mod.morale_check({"name": "G", "morale": 8}, adjustments=99, rng=_FixedRng(10))
    lo = combat_mod.morale_check({"name": "G", "morale": 8}, adjustments=-99, rng=_FixedRng(10))
    assert hi["adjustments"] == 4 and hi["bonus"] == 5
    assert lo["adjustments"] == -4 and lo["bonus"] == -3


class _FixedRng:
    def __init__(self, v):
        self.v = v

    def randbelow(self, n):
        return self.v - 1


def test_ensure_morale_defaults_old_state():
    # Gamla states utan fälten → defaults, ingen KeyError (§1.1)
    e = combat_mod.ensure_morale({"name": "Old"})
    assert e["morale"] == 8 and e["morale_mod"] == 1
    assert e["morale_checked"] == [] and e["morale_state"] == "steady"
    garbage = combat_mod.ensure_morale({"name": "G", "morale": "x"})
    assert garbage["morale"] == 8
    low = combat_mod.ensure_morale({"name": "G", "morale": 2})
    assert low["morale_mod"] == -5


# ─────────────────────────────────────────────────────────────
# 2. Triggers — first_casualty / half_down / leader_down / fear_effect
# ─────────────────────────────────────────────────────────────

def test_first_casualty_duplicate_names(monkeypatch):
    """3× 'Guard' — döda en → exakt de 2 överlevande checkar EN gång."""
    state = make_state(GUARD3)
    cbt = state["world"]["combat"]
    cbt["enemies"][0]["alive"] = False  # Guard#0 stupar (t.ex. status-död)

    force_rolls(monkeypatch, [12, 12])
    effects = guardian.apply_mechanics(state, {})
    me = morale_effects(effects)
    assert [(m["value"], m["trigger"]) for m in me] == [
        ("Guard#1", "first_casualty"), ("Guard#2", "first_casualty")]
    assert cbt["enemies"][1]["morale_checked"] == ["first_casualty"]
    assert cbt["enemies"][2]["morale_checked"] == ["first_casualty"]
    assert cbt["enemies"][1]["morale_state"] == "wavering"  # 13 → waver

    # Idempotence: omkörning + ny begäran → noll nya prov (per (target, trigger))
    effects2 = guardian.apply_mechanics(state, {
        "morale_checks": [{"target": "all", "trigger": "first_casualty", "note": "igen"}]})
    assert morale_effects(effects2) == []


def test_half_down_trigger_isolated(monkeypatch):
    state = make_state(GUARD3)
    cbt = state["world"]["combat"]
    cbt["enemies"][0]["alive"] = False
    cbt["enemies"][2]["alive"] = False  # 1 av 3 kvar → half_down
    # isolera: first_casualty + leader_down redan checkade (Guard#1 = ledarens
    # sidokandidat; ledaren Guard#1 lever → bara half_down kvar)
    cbt["enemies"][1]["morale_checked"] = ["first_casualty", "leader_down"]

    force_rolls(monkeypatch, [20])
    effects = guardian.apply_mechanics(state, {})
    me = morale_effects(effects)
    assert len(me) == 1 and me[0]["trigger"] == "half_down" and me[0]["value"] == "Guard#1"
    assert me[0]["outcome"] == "fight_on"


def test_leader_down_trigger_isolated(monkeypatch):
    specs = [{"name": "Guard", "hp": 10, "ac": 14, "morale": 9, "leader": True},
             {"name": "Guard", "hp": 10, "ac": 14, "morale": 7}]
    state = make_state(specs)
    cbt = state["world"]["combat"]
    cbt["enemies"][0]["alive"] = False  # ledaren stupar
    cbt["enemies"][1]["morale_checked"] = ["first_casualty", "half_down"]

    force_rolls(monkeypatch, [15])
    effects = guardian.apply_mechanics(state, {})
    me = morale_effects(effects)
    assert len(me) == 1 and me[0]["trigger"] == "leader_down" and me[0]["value"] == "Guard#1"
    # justeringar: leader_down −2 + sidan förlorar hårt −2 = −4 (klampat)
    assert me[0]["bonus"] == 7 - 7 - 4 + 0 or me[0]["bonus"] == -4
    assert me[0]["outcome"] == "waver"


def test_morale_triggers_for_conditions():
    # Ren detektor: fear_effect detekteras ALDRIG automatiskt (§1.2)
    state = make_state(GUARD3)
    cbt = state["world"]["combat"]
    assert combat_mod.morale_triggers_for(state, cbt) == []  # alla lever
    cbt["enemies"][0]["alive"] = False
    toks = [t["trigger"] for t in combat_mod.morale_triggers_for(state, cbt)]
    assert toks == ["first_casualty"]
    cbt["enemies"][1]["alive"] = False  # 1/3 kvar → half_down (+ ledaren
    # Guard#1 (högst moral) är också död → leader_down enligt §1.2)
    toks = [t["trigger"] for t in combat_mod.morale_triggers_for(state, cbt)]
    assert toks == ["first_casualty", "half_down", "leader_down"]
    assert "fear_effect" not in toks  # ALDRIG automatiskt (§1.2)
    cbt["enemies"][2]["alive"] = False  # alla döda → inga levande att checka
    # (detektorn rapporterar villkoren; applicatorn no-opar utan levande mål)


def test_fear_effect_request_targets_all_duplicates(monkeypatch):
    """'all' + namn-matchning slår ALLA dublettnamn (3× 'Guard')."""
    specs = [{"name": "Guard", "hp": 10, "ac": 12, "morale": 10} for _ in range(3)]
    state = make_state(specs)
    force_rolls(monkeypatch, [5, 5, 5])
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "all", "trigger": "fear_effect", "note": "drakskrämsel"}]})
    me = morale_effects(effects)
    assert [m["value"] for m in me] == ["Guard#0", "Guard#1", "Guard#2"]
    assert all(m["trigger"] == "fear_effect" for m in me)
    assert all(m["outcome"] == "flee" for m in me)
    # dedup per (target, trigger) i samma batch + cross-call idempotence
    effects2 = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "all", "trigger": "fear_effect", "note": "igen"},
        {"target": "all", "trigger": "fear_effect", "note": "dubblett-samma-tur"}]})
    assert morale_effects(effects2) == []


def test_named_target_matches_every_duplicate(monkeypatch):
    specs = [{"name": "Guard", "hp": 10, "ac": 12, "morale": 10} for _ in range(3)]
    state = make_state(specs)
    force_rolls(monkeypatch, [14, 14, 14])
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "guard", "trigger": "fear_effect", "note": ""}]})
    me = morale_effects(effects)
    assert [m["value"] for m in me] == ["Guard#0", "Guard#1", "Guard#2"]


# ─────────────────────────────────────────────────────────────
# 3. Utfalls-applicering (§1.5) — waver / flee / surrender / fight_on
# ─────────────────────────────────────────────────────────────

def test_waver_and_fight_on_application(monkeypatch):
    state = make_state([{"name": "Goblin", "hp": 7, "ac": 12, "morale": 8}])
    cbt = state["world"]["combat"]
    force_rolls(monkeypatch, [11])  # total 12 → waver
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "goblin", "trigger": "fear_effect", "note": ""}]})
    g = cbt["enemies"][0]
    assert g["morale_state"] == "wavering" and g["alive"] is True
    assert morale_effects(effects)[0]["outcome"] == "waver"

    force_rolls(monkeypatch, [20])  # fight_on (annan trigger)
    effects2 = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "goblin", "trigger": "half_down", "note": ""}]})
    assert morale_effects(effects2)[0]["outcome"] == "fight_on"
    assert g["alive"] is True and g.get("fled") is None
    # fight_on är tyst i summaries — inga extra effekter
    assert [e["type"] for e in effects2] == ["morale_check"]


def test_flee_application_routing(monkeypatch):
    state = make_state([{"name": "Bandit", "hp": 9, "ac": 12, "morale": 8}])
    cbt = state["world"]["combat"]
    cbt["round_acted"] = {"player": True, "enemies": {"Bandit#0": False}}
    force_rolls(monkeypatch, [7])  # total 8 → flee
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "bandit", "trigger": "fear_effect", "note": ""}]})
    b = cbt["enemies"][0]
    assert b["morale_state"] == "routed" and b["fled"] is True and b["alive"] is False
    assert b["hp"] == 9  # HP bevaras — de lever i fiktionen (§1.5)
    # ingen XP-effekt för flydde
    assert not any(e["type"] == "xp" for e in effects)
    assert {"type": "enemy_fled", "value": "Bandit"} in effects
    # rund-bokföring: rundor väntar inte på flyktingar
    assert not cbt["round_acted"]["enemies"].get("Bandit#0")
    # loggrader: morale check-raden + 'routs and flees!'-raden (§1.3/§1.5)
    texts = [r["text"] for r in cbt["log"]]
    assert any(t.startswith("morale check (🎲 d20=7") for t in texts)
    assert any(t == "routs and flees!" for t in texts)


def test_surrender_application(monkeypatch):
    state = make_state([{"name": "Kerker", "hp": 5, "ac": 10, "morale": 2}])
    cbt = state["world"]["combat"]
    force_rolls(monkeypatch, [1])  # total −4 → surrender
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "kerker", "trigger": "fear_effect", "note": ""}]})
    k = cbt["enemies"][0]
    assert k["morale_state"] == "broken" and k["surrendered"] is True and k["alive"] is False
    assert morale_effects(effects)[0]["outcome"] == "surrender"
    # alla ute → striden slut, korrekt combat_end.value (§1.5)
    ends = [e for e in effects if e["type"] == "combat_end"]
    assert len(ends) == 1 and ends[0]["value"] == "enemies surrendered"
    assert cbt["active"] is False


def test_flee_impossible_becomes_surrender(monkeypatch):
    state = make_state([{"name": "Hörnad", "hp": 4, "ac": 10, "morale": 8}])
    cbt = state["world"]["combat"]
    cbt["chase"] = {"active": True, "mode": "player_flee"}  # flykt omöjlig (§1.3)
    force_rolls(monkeypatch, [7])  # flee-band → konverteras
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "hörnad", "trigger": "fear_effect", "note": ""}]})
    h = cbt["enemies"][0]
    assert h["surrendered"] is True and h.get("fled") is None
    assert morale_effects(effects)[0]["outcome"] == "surrender"
    ends = [e for e in effects if e["type"] == "combat_end"]
    assert ends and ends[0]["value"] == "enemies surrendered"


def test_all_flee_gives_enemies_fled_end(monkeypatch):
    specs = [{"name": "Guard", "hp": 10, "ac": 12, "morale": 10} for _ in range(3)]
    state = make_state(specs)
    cbt = state["world"]["combat"]
    force_rolls(monkeypatch, [5, 5, 5])
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "all", "trigger": "fear_effect", "note": ""}]})
    ends = [e for e in effects if e["type"] == "combat_end"]
    assert len(ends) == 1 and ends[0]["value"] == "enemies fled"
    assert cbt["active"] is False


def test_morale_12_fanatic_skips_via_apply(monkeypatch):
    state = make_state([{"name": "Fanatiker", "hp": 10, "ac": 14, "morale": 12}])
    cbt = state["world"]["combat"]
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "fanatiker", "trigger": "fear_effect", "note": ""}]})
    me = morale_effects(effects)
    assert len(me) == 1 and me[0]["outcome"] == "fight_on" and me[0]["skipped"] is True
    assert cbt["enemies"][0]["alive"] is True
    # ingen morale check-loggrad för skip
    assert not any(r["text"].startswith("morale check") for r in cbt["log"])


def test_validation_drops_bad_entries(monkeypatch):
    state = make_state([{"name": "Guard", "hp": 10, "ac": 12, "morale": 8}])
    force_rolls(monkeypatch, [20])
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "", "trigger": "fear_effect"},
        {"target": "guard", "trigger": "bogus_trigger"},
        "notadict",
        {"target": "nosuchenemy", "trigger": "fear_effect"},
    ]})
    assert morale_effects(effects) == []  # ingen exception, inga falska prov


def test_old_state_tolerance_apply(monkeypatch):
    # Handbyggd gamla-varianten combat: inga moral-fält, ingen morale_auto
    state = {"meta": {"turn_count": 1},
             "character": {"hp": {"current": 10, "max": 10, "temp": 0}}}
    state["world"] = {"combat": {"active": True, "round": 1, "enemies": [
        {"name": "Old", "hp": 5, "max_hp": 5, "ac": 10, "alive": True}], "log": []}}
    force_rolls(monkeypatch, [20])
    effects = guardian.apply_mechanics(state, {"morale_checks": [
        {"target": "old", "trigger": "fear_effect", "note": ""}]})
    me = morale_effects(effects)
    assert len(me) == 1 and me[0]["outcome"] == "fight_on"
    e = state["world"]["combat"]["enemies"][0]
    assert e["morale"] == 8 and e["morale_checked"] == ["fear_effect"]


# ─────────────────────────────────────────────────────────────
# 4. _end_combat — double-end-guard
# ─────────────────────────────────────────────────────────────

def test_end_combat_double_end_guard():
    state = make_state([{"name": "Guard", "hp": 10, "ac": 12, "morale": 8}])
    effects = []
    assert guardian._end_combat(state, "all defeated", effects) is True
    ended_turn = state["world"]["combat"]["ended_turn"]
    # andra anropet ska vara en ren no-op (§2.3 double-end-guard)
    assert guardian._end_combat(state, "all defeated", effects) is False
    assert guardian._end_combat(state, "enemies fled", effects) is False
    ends = [e for e in effects if e["type"] == "combat_end"]
    assert len(ends) == 1 and ends[0]["value"] == "all defeated"
    assert state["world"]["combat"]["ended_turn"] == ended_turn
    assert state["world"]["combat"]["active"] is False


def test_end_combat_reason_mixed_deaths():
    cbt = {"enemies": [{"alive": False, "hp": 0}, {"alive": False, "fled": True}]}
    assert guardian._combat_end_reason(cbt) == "all defeated"
    cbt2 = {"enemies": [{"alive": False, "fled": True}, {"alive": False, "fled": True}]}
    assert guardian._combat_end_reason(cbt2) == "enemies fled"
    cbt3 = {"enemies": [{"alive": False, "surrendered": True}]}
    assert guardian._combat_end_reason(cbt3) == "enemies surrendered"


# ─────────────────────────────────────────────────────────────
# 5. [COMBAT:]-tagg-emission + summaries + [MORALE:]-tagg-paritet
# ─────────────────────────────────────────────────────────────

def test_format_guardian_summary_sv_en():
    effects = [
        {"type": "morale_check", "value": "Guard#0", "name": "Guard", "d20": 11, "bonus": 1,
         "total": 12, "dc": 10, "outcome": "waver", "trigger": "fear_effect"},
        {"type": "morale_check", "value": "Guard#1", "name": "Guard", "d20": 7, "bonus": 1,
         "total": 8, "dc": 10, "outcome": "flee", "trigger": "fear_effect"},
        {"type": "morale_check", "value": "Guard#2", "name": "Guard", "d20": 1, "bonus": -2,
         "total": -1, "dc": 10, "outcome": "surrender", "trigger": "leader_down"},
        {"type": "morale_check", "value": "Guard#3", "name": "Guard", "d20": 20, "bonus": 1,
         "total": 21, "dc": 10, "outcome": "fight_on", "trigger": "first_casualty"},
    ]
    state = make_state(GUARD3)
    sv = guardian.format_guardian_summary(effects, state, language="sv")
    en = guardian.format_guardian_summary(effects, state, language="en")
    assert sv.count("🏳️") == 3  # fight_on är tyst (§1.3)
    assert "tar ett moralprov" in sv and "flyr!" in sv and "ger upp!" in sv
    assert "takes a morale check" in en and "flees!" in en and "surrenders!" in en
    assert "fight_on" not in sv and "holds!" not in sv


def test_morale_check_emits_combat_tag():
    # §1.4: morale_check i _changed-mängden → [COMBAT:]-taggen firear
    state = make_state(GUARD3)
    effects = [{"type": "morale_check", "value": "Guard#1", "name": "Guard", "d20": 7,
                "bonus": 1, "total": 8, "dc": 10, "outcome": "flee", "trigger": "fear_effect"}]
    out = guardian.format_guardian_summary(effects, state, language="sv")
    assert "[COMBAT:" in out


def test_morale_tag_path_parity(monkeypatch):
    """[MORALE:]-taggen och Guardian-vägen → samma slutstate (§4.2)."""
    import main

    mech = {"morale_checks": [{"target": "guard", "trigger": "fear_effect", "note": ""}]}
    state_a = make_state(GUARD3)
    force_rolls(monkeypatch, [12, 12, 12])
    guardian.apply_mechanics(state_a, dict(mech))

    state_b = make_state(GUARD3)
    force_rolls(monkeypatch, [12, 12, 12])
    clean, _state, effects_b = main._parse_mechanical_tags(
        "Goblinerna tvekar. [MORALE:guard|fear_effect]", state_b)

    assert "[MORALE:" not in clean  # taggen strippas ur narrativet
    assert state_b["meta"]["combat_tag_dirty"] is True
    snap_a = [(e["morale"], e["morale_mod"], e["morale_checked"], e["morale_state"])
              for e in state_a["world"]["combat"]["enemies"]]
    snap_b = [(e["morale"], e["morale_mod"], e["morale_checked"], e["morale_state"])
              for e in state_b["world"]["combat"]["enemies"]]
    assert snap_a == snap_b
    assert [(m["value"], m["outcome"]) for m in morale_effects(effects_b)] == \
           [("Guard#0", "waver"), ("Guard#1", "waver"), ("Guard#2", "waver")]
