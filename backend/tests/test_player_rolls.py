"""Tester för player_rolls — pre-DM-spelarattack (P0).

Riktiga [Resultat:]-rader från frankdetanks transkript används som fixture:
de är produktionsformatet, inte påhittade exempel.
"""
import pytest

import combat
import player_rolls as pr


def _state(**over):
    st = {
        "meta": {},
        "character": {
            "name": "Pemba",
            "class": "Ranger",
            "level": 2,
            "features": [{"name": "Sharpshooter (Variant Human feat)"}],
        },
        "inventory": [
            {"name": "Yew Longbow", "damage_dice": "1d8", "equipped": True,
             "usage": "wielded", "magic_bonus": 0},
            {"name": "Bedroll", "damage_dice": None, "equipped": False},
        ],
        "world": {"combat": {"active": True, "round": 1, "enemies": [
            {"id": 0, "name": "Tally-Keeper", "hp": 11, "max_hp": 11, "ac": 13, "alive": True},
        ]}},
        "npcs": [
            {"name": "Branneth", "relation": "allierad"},
            {"name": "Mara", "relation": "allierad"},
            {"name": "Tally-Keeper", "relation": "fiende"},
        ],
    }
    st.update(over)
    return st


@pytest.fixture
def fixed_dice(monkeypatch):
    """Ersätter tärningsmotorn: alltid 5 på varje tärning."""
    monkeypatch.setattr(combat, "roll_dice", lambda notation: (5, [5]))


# ── parse_attack_result: riktiga produktionsrader ──────────────────────

@pytest.mark.parametrize("line,hit,total,ac,crit", [
    ("[Resultat: ATTACK vs AC 13 → 14 (8+6)]", True, 14, 13, False),
    ("[Resultat: ATTACK vs AC 13 → 13 (7+6)]", True, 13, 13, False),
    ("[Resultat: ATTACK vs AC 16 → 12 (7+5)]", False, 12, 16, False),
    ("[Resultat: ATTACK vs AC 16 → 24 (19+5)]", True, 24, 16, False),
    ("[Resultat: ATTACK vs AC 13 (Sharpshooter −5/+10) ADVANTAGE → 18 (17, 13+1)]", True, 18, 13, False),
    ("[Resultat: SHARPSHOOTER ATTACK vs Lead Worg Rider AC 13 → 24 (19+5)]", True, 24, 13, False),
    ("[Resultat: Pemba's longbow attack vs Orc (Cover) AC 13 → 14 (8+6)]", True, 14, 13, False),
    ("[Resultat: RANGED ATTACK (IMPROVISED STONE) vs AC 14 → 5 (4+1)]", False, 5, 14, False),
])
def test_parse_real_lines(line, hit, total, ac, crit):
    got = pr.parse_attack_result(line)
    assert got is not None, line
    assert got["hit"] is hit
    assert got["total"] == total
    assert got["ac"] == ac
    assert got["crit"] is crit


def test_parse_natural_20_is_crit():
    got = pr.parse_attack_result("[Resultat: ATTACK vs AC 13 → 20 (20+5)]")
    assert got["crit"] is True and got["hit"] is True and got["nat"] == 20


def test_parse_natural_1_misses():
    got = pr.parse_attack_result("[Resultat: ATTACK vs AC 13 → 6 (1+5)]")
    assert got["hit"] is False and got["nat"] == 1


@pytest.mark.parametrize("line", [
    "[Resultat: PERCEPTION (DC 12) → 9 (5+4)]",
    "[Resultat: DEATH SAVE (DC 10) → 1 (1)]",
    "[Resultat: STEALTH (DC 14) DISADVANTAGE → 15 (17, 13+1)]",
    "[Resultat: ATTACK (SHARPSHOOTER −5) vs AC → 18 (12+6)]",  # AC utan tal
    "Shoot false pemba with a normal shot",                     # ingen Resultat-rad
])
def test_parse_non_attack_lines_return_none(line):
    assert pr.parse_attack_result(line) is None


# ── tredjeparts-rullningar ─────────────────────────────────────────────

def test_foreign_roll_ally_target():
    st = _state()
    line = "[Resultat: ATTACK vs AC 13 (Lone Worg bite vs Mara) → 15 (12+3)]"
    assert pr._foreign_roll(line, st) is True
    assert pr.plan_player_attack(st, line) is None


def test_own_attack_at_named_enemy_is_not_foreign():
    st = _state()
    line = "[Resultat: Pemba's longbow attack vs Orc (Cover) AC 13 → 14 (8+6)]"
    assert pr._foreign_roll(line, st) is False


# ── plan_player_attack ─────────────────────────────────────────────────

def test_plan_rolls_weapon_damage(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]")
    assert plan is not None
    assert plan["hit"] is True
    assert plan["damage"] == 5           # 1d8 = 5, ingen bonus på ren ATTACK
    assert plan["notation"] == "1d8"
    assert st["meta"][pr.PLAN_KEY]["damage"] == 5


def test_plan_adds_sharpshooter_bonus(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(
        st, "[Resultat: ATTACK vs AC 13 (Sharpshooter −5/+10) → 18 (17+1)]")
    assert plan["damage"] == 15          # 1d8=5 +10 Sharpshooter
    assert "Sharpshooter +10" in plan["notes"]


def test_plan_without_sharpshooter_feature_gets_no_bonus(fixed_dice):
    st = _state()
    st["character"]["features"] = []
    plan = pr.plan_player_attack(
        st, "[Resultat: ATTACK vs AC 13 (Sharpshooter −5/+10) → 18 (17+1)]")
    assert plan["damage"] == 5
    assert plan["notes"] == []


def test_plan_crit_doubles_dice(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 20 (20+0)]")
    assert plan["crit"] is True
    assert plan["damage"] == 10          # 1d8 två gånger


def test_plan_miss_still_has_no_damage_claim(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 16 → 12 (7+5)]")
    assert plan["hit"] is False
    assert "damage" in plan               # rullad, men DM-blocket visar den inte


def test_plan_cleared_on_non_attack_turn(fixed_dice):
    st = _state()
    pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]")
    assert pr.PLAN_KEY in st["meta"]
    pr.plan_player_attack(st, "Read the tracks, prepare for more ambushes")
    assert pr.PLAN_KEY not in st["meta"]


def test_plan_cleared_when_combat_inactive(fixed_dice):
    st = _state()
    st["world"]["combat"]["active"] = False
    assert pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]") is None
    assert pr.PLAN_KEY not in st["meta"]


def test_plan_is_idempotent_for_same_message(fixed_dice):
    st = _state()
    line = "[Resultat: ATTACK vs AC 13 → 14 (8+6)]"
    first = pr.plan_player_attack(st, line)
    second = pr.plan_player_attack(st, line)
    assert first["damage"] == second["damage"]


def test_plan_without_weapon_returns_none(fixed_dice):
    st = _state()
    st["inventory"] = [{"name": "Bedroll"}]
    assert pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]") is None
    assert pr.PLAN_KEY not in st["meta"]


# ── consume ────────────────────────────────────────────────────────────

def test_consume_pops_plan(fixed_dice):
    st = _state()
    line = "[Resultat: ATTACK vs AC 13 → 14 (8+6)]"
    pr.plan_player_attack(st, line)
    got = pr.consume_player_attack(st, line)
    assert got and got["damage"] == 5
    assert pr.PLAN_KEY not in st["meta"]


def test_consume_rejects_other_turns_message(fixed_dice):
    st = _state()
    pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]")
    assert pr.consume_player_attack(st, "ett helt annat meddelande") is None
    assert pr.PLAN_KEY in st["meta"]      # planen är kvar för rätt tur


# ── DM-block ───────────────────────────────────────────────────────────

def test_format_block_states_hit_and_damage(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]")
    sv = pr.format_attack_block(plan, "sv")
    en = pr.format_attack_block(plan, "en")
    assert "HIT" in sv and "5 damage" in sv
    assert "HIT" in en and "5 damage" in en


def test_format_block_miss_has_no_damage_bit(fixed_dice):
    st = _state()
    plan = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 16 → 12 (7+5)]")
    en = pr.format_attack_block(plan, "en")
    verdict_line = [l for l in en.splitlines() if l.startswith("**")][0]
    assert verdict_line == "**MISS — 12 vs AC 16**"
    assert "damage" not in verdict_line


def test_format_block_hit_and_crit_verdicts(fixed_dice):
    st = _state()
    hit = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 14 (8+6)]")
    assert pr.format_attack_block(hit, "en").splitlines()[2] == "**HIT — 14 vs AC 13** · **5 damage** (1d8)"
    crit = pr.plan_player_attack(st, "[Resultat: ATTACK vs AC 13 → 20 (20+0)]")
    crit_block = pr.format_attack_block(crit, "en")
    assert crit_block.splitlines()[2].startswith("**CRITICAL HIT — 20 vs AC 13**")
    assert "×2 crit" in crit_block

# ── Guardian-integration: planen slår LLM:ens siffror ──────────────────

def _combat_state():
    return {
        "character": {"name": "Pemba", "class": "ranger", "level": 2,
                      "hp": {"current": 19, "max": 19}, "ac": 15,
                      "features": [{"name": "Sharpshooter"}], "statuses": []},
        "inventory": [{"name": "Yew Longbow", "damage_dice": "1d8",
                       "equipped": True, "usage": "wielded", "magic_bonus": 0}],
        "npcs": [], "currency": {}, "quests": [],
        "meta": {"turn_count": 10},
        "world": {"combat": {
            "active": True, "round": 1, "phase": "active", "turn_order": [],
            "current_index": 0, "player_actions": {"action": True, "bonus": True, "reaction": True},
            "enemies": [{"id": 0, "name": "Tally-Keeper", "hp": 11, "max_hp": 11,
                         "ac": 13, "alive": True, "statuses": []}],
            "allies": [], "log": [],
        }},
    }


def test_guardian_prefers_plan_over_llm(monkeypatch):
    """LLM säger miss — men planen (18 vs AC 13) säger HIT med 5 skada."""
    import guardian
    st = _combat_state()
    line = "[Resultat: ATTACK vs AC 13 → 18 (17+1)]"
    plan = pr.plan_player_attack(st, line)
    assert plan and plan["hit"] is True
    st["meta"][pr.PLAN_KEY]["damage"] = 5          # fast skada, ingen tärning
    guardian.apply_mechanics(st, {"player_attacks": [
        {"target": "Tally-Keeper", "hit": False, "damage": 0}]})
    enemy = st["world"]["combat"]["enemies"][0]
    assert enemy["hp"] == 6, "planen ska vara auktoritativ: 11 - 5 = 6"
    assert pr.PLAN_KEY not in st["meta"], "planen ska förbrukas"


def test_guardian_plan_miss_blocks_llm_hit(monkeypatch):
    """LLM säger hit med 9 skada — men planen (12 vs AC 16) säger MISS."""
    import guardian
    st = _combat_state()
    st["world"]["combat"]["enemies"][0]["ac"] = 16
    line = "[Resultat: ATTACK vs AC 16 → 12 (7+5)]"
    plan = pr.plan_player_attack(st, line)
    assert plan and plan["hit"] is False
    guardian.apply_mechanics(st, {"player_attacks": [
        {"target": "Tally-Keeper", "hit": True, "damage": 9}]})
    enemy = st["world"]["combat"]["enemies"][0]
    assert enemy["hp"] == 11, "en miss får aldrig bli skada"
    assert pr.PLAN_KEY not in st["meta"], "miss-planen ska också förbrukas"


def test_guardian_without_plan_still_rolls_weapon_dice(monkeypatch):
    """Bakåtkompatibilitet: ingen plan → gamla vägen (motorn rullar 1d8)."""
    import guardian
    st = _combat_state()
    monkeypatch.setattr(combat, "roll_dice", lambda notation: (7, [7]))
    guardian.apply_mechanics(st, {"player_attacks": [
        {"target": "Tally-Keeper", "hit": True, "damage": 99}]})
    enemy = st["world"]["combat"]["enemies"][0]
    assert enemy["hp"] == 4, "motorn rullar 7 — LLM:ens 99 ignoreras"


# ── Halvkastare: ranger/paladin får slots vid level-up ─────────────────

def test_half_casters_are_in_slot_table():
    import guardian
    assert guardian._SPELL_SLOTS_BY_LEVEL["ranger"][2] == 2
    assert guardian._SPELL_SLOTS_BY_LEVEL["paladin"][2] == 2
    assert guardian._SPELL_SLOTS_BY_LEVEL["ranger"][1] == 0   # 5e: inga slots på nivå 1
    assert guardian._SPELL_SLOTS_BY_LEVEL["ranger"][5] == 4


def test_ranger_level_up_grants_slots():
    import guardian
    ch = {"name": "Pemba", "class": "ranger", "level": 2,
          "hp": {"current": 12, "max": 12}, "abilities": {"CON": {"mod": 2}},
          "spell_slots": {"current": 0, "max": 0}, "hit_dice": {"dice": "1d10", "total": 1, "remaining": 1},
          "proficiency": 2}
    effects = []
    guardian._apply_level_up_bonuses(ch, effects)
    assert ch["spell_slots"] == {"current": 2, "max": 2}
    assert any(e.get("type") == "spell_slots_up" for e in effects)


@pytest.mark.asyncio
async def test_guardian_call_falls_back_when_model_raises(monkeypatch):
    """Timeout från den valda guardian-modellen får inte tysta mekaniken."""
    import main
    seen = []

    async def fake_call(model, messages, **kw):
        seen.append(model)
        if model == "deepseek-test-model":
            raise RuntimeError("timeout")
        return '{"ok": true}'

    monkeypatch.setattr(main, "_call_llm", fake_call)
    monkeypatch.setattr(main, "_guardian_model_for", lambda state: "deepseek-test-model")
    raw = await main._guardian_call({}, [], {})
    assert raw == '{"ok": true}'
    assert seen == ["deepseek-test-model", main.GUARDIAN_MODEL]
