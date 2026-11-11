"""W2A guardian.py hardening (2026-09-06) — audit-mechanics.md §3/§4/§5/§6.

Täcker:
  - P0 krasch-härdighet: _safe_int-sweep (non-numeric/null LLM-värden), hp:null (bug 7)
  - [COMBAT:]-tagg-emission för enemy_hit/enemy_miss + mech-nycklar (bug 4)
  - Live-path JSON-trunkeringsreparation i _parse_json (§4)
  - Död Battle-AI borttagen (§6)
  - Level-up-konsolidering: while-loop, ingen xp_gain>0-gate, next_level från
    _XP_THRESHOLDS (§5)
  - format_guardian_summary: nya renderingsfall (spell slots, inspiration,
    exhaustion, spells, vila, träning, cover, npc_near) (§4c)
"""

import json
import sys
from urllib.parse import unquote
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


def _make_state(hp=14) -> dict:
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


# ══ P0-kraschhärdighet: non-numeric / null LLM-värden (bug 2) ══════════

def test_damage_amount_non_numeric_no_crash():
    state = _make_state()
    effects = guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": "1d8+2", "type": "slashing"}]),
        skip_effects=[],
    )
    # "1d8+2" → _safe_int → 0 → ingen skada applicerad, ingen krasch
    assert state["character"]["hp"]["current"] == 14
    assert not any(e["type"] == "skada" for e in effects)


def test_damage_amount_null_no_crash():
    state = _make_state()
    guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": None}]), skip_effects=[]
    )
    assert state["character"]["hp"]["current"] == 14


def test_healing_amount_non_numeric_no_crash():
    state = _make_state(hp=5)
    guardian.apply_mechanics(
        state, _mech(healing=[{"target": "player", "amount": "2d4+2", "type": "potion"}]),
        skip_effects=[],
    )
    # Ingen krasch; potion-nätet ger roll_grant, HP orört av det trasiga beloppet
    assert state["character"]["hp"]["current"] == 5


def test_currency_amount_non_numeric_no_crash():
    state = _make_state()
    state["currency"] = {"pp": 0, "gp": 5, "sp": 0, "cp": 0}
    guardian.apply_mechanics(
        state, _mech(currency=[{"denom": "gp", "amount": "tio"}]), skip_effects=[]
    )
    assert state["currency"]["gp"] == 5


def test_quest_xp_reward_non_numeric_no_crash():
    state = _make_state()
    guardian.apply_mechanics(
        state, _mech(quests_new=[{"name": "Uppdrag X", "xp_reward": "massor"}]),
        skip_effects=[],
    )
    q = state["quests"][0]
    assert q["xp_reward"] == 100  # default vid trasigt värde


def test_player_attack_damage_non_numeric_no_crash():
    state = _make_state()
    combat.start_combat(state, [{"name": "Goblin", "hp": 7, "ac": 12}])
    guardian.apply_mechanics(
        state, _mech(player_attacks=[{"target": "Goblin", "hit": True, "damage": "1d8+2"}]),
        skip_effects=[],
    )
    enemy = state["world"]["combat"]["enemies"][0]
    assert enemy["hp"] == 7  # trasigt tal → 0 skada, ingen krasch


def test_ally_damage_amount_null_no_crash():
    state = _make_state()
    c = combat.start_combat(state, [{"name": "Goblin", "hp": 7, "ac": 12}])
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    guardian.apply_mechanics(
        state, _mech(ally_damage=[{"ally": "Mimmrick", "amount": None, "attacker": "Goblin"}]),
        skip_effects=[],
    )
    assert c["allies"][0]["hp"] == 10


def test_enemy_attack_off_list_damage_non_numeric_no_crash(monkeypatch):
    """Off-list attacker med non-numeric claim '1d6+1' → ingen krasch, och P0:
    skadan RULLAS av servern (heuristiska stats) — DM:ens claim appliceras aldrig
    (gamla beteendet: claim → _safe_int → 0 skada; stale-test uppdaterat 2026-09-22)."""
    state = _make_state()
    combat.start_combat(state, [{"name": "Goblin", "hp": 7, "ac": 12}])
    _mock_dice(monkeypatch, d20_seq=[], dmg_seq=[])
    guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Okänd Strykare", "hit": True, "damage": "1d6+1"}]),
        skip_effects=[],
    )
    # Server-rullad skada (mockade tärningar: d20=10 → 13 vs AC 12 → träff, 1 dmg)
    assert state["character"]["hp"]["current"] == 13


def test_player_ac_null_no_crash(monkeypatch):
    """ac: null på karaktären → _safe_int default 10 (bug 2, :2464)."""
    state = _make_state()
    state["character"]["ac"] = None
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[18], dmg_seq=[(3, [3])])
    effects = guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Vakt"}]), skip_effects=[]
    )
    assert any(e["type"] == "enemy_hit" for e in effects)  # 18+3 vs AC 10 → träff


# ══ P0 hp:null (bug 7) ══════════════════════════════════════════════════

def test_hp_null_apply_mechanics_no_crash():
    state = _make_state()
    state["character"]["hp"] = None
    effects = guardian.apply_mechanics(
        state, _mech(damage=[{"target": "player", "amount": 3, "type": "bludgeoning"}]),
        skip_effects=[],
    )
    hp = state["character"]["hp"]
    assert isinstance(hp, dict)
    assert any(e["type"] == "skada" for e in effects)


def test_hp_null_enemy_attack_path_no_crash(monkeypatch):
    state = _make_state()
    state["character"]["hp"] = None
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[18], dmg_seq=[(3, [3])])
    guardian.apply_mechanics(
        state, _mech(enemy_attacks=[{"attacker": "Vakt"}]), skip_effects=[]
    )
    hp = state["character"]["hp"]
    assert isinstance(hp, dict)
    assert hp["current"] == max(0, hp["max"] - 3)


def test_hp_null_format_summary_no_crash():
    state = _make_state()
    state["character"]["hp"] = None
    out = guardian.format_guardian_summary(
        [{"type": "skada", "value": 3}], state, "sv", mech=_mech(),
    )
    assert "Lorekeeper" in out  # ingen AttributeError


# ══ [COMBAT:]-tagg-emission (bug 4) ═════════════════════════════════════

def test_enemy_hit_alone_emits_combat_tag_with_player_hp(monkeypatch):
    state = _make_state(hp=14)
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[18], dmg_seq=[(3, [3])])
    mech = _mech(enemy_attacks=[{"attacker": "Vakt"}])
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])
    assert [e["type"] for e in effects] == ["enemy_hit"] or any(e["type"] == "enemy_hit" for e in effects)

    out = guardian.format_guardian_summary(effects, state, "sv", mech=mech)
    assert "[COMBAT:" in out, "enemy_hit-tur måste emittera [COMBAT:]-taggen"
    assert out.rstrip().endswith("]")
    tag_payload = out[out.find("[COMBAT:") + len("[COMBAT:"):-1]
    decoded = unquote(tag_payload)
    assert "player_hp" in decoded, "taggen måste innehålla player_hp-injektionen"
    data = json.loads(decoded)
    assert data["player_hp"] == {"current": 11, "max": 14}


def test_enemy_miss_alone_emits_combat_tag(monkeypatch):
    state = _make_state(hp=14)
    combat.start_combat(state, [{"name": "Vakt", "hp": 7, "ac": 20, "attack_bonus": 0, "damage_dice": "1d6"}])
    _mock_dice(monkeypatch, d20_seq=[1], dmg_seq=[])  # nat 1 → fumble/miss
    mech = _mech(enemy_attacks=[{"attacker": "Vakt"}])
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])
    assert any(e["type"] == "enemy_miss" for e in effects)
    out = guardian.format_guardian_summary(effects, state, "sv", mech=mech)
    assert "[COMBAT:" in out
    assert "player_hp" in unquote(out[out.find("[COMBAT:") + 8:-1])


def test_player_miss_only_still_emits_tag_via_mech_keys():
    """Spelarens miss (effects tomma) men player_attacks i mech → tagg via mech-tupeln."""
    state = _make_state()
    combat.start_combat(state, [{"name": "Goblin", "hp": 7, "ac": 12}])
    mech = _mech(player_attacks=[{"target": "Goblin", "hit": False}])
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])
    out = guardian.format_guardian_summary(effects, state, "sv", mech=mech)
    assert "[COMBAT:" in out


def test_combat_events_only_emits_tag():
    state = _make_state()
    combat.start_combat(state, [{"name": "Goblin", "hp": 7, "ac": 12}])
    mech = _mech(combat_events=["Goblinen morrar hotfullt"])
    effects = guardian.apply_mechanics(state, mech, skip_effects=[])
    out = guardian.format_guardian_summary(effects, state, "sv", mech=mech)
    assert "[COMBAT:" in out


def test_no_combat_tag_outside_combat():
    state = _make_state()
    out = guardian.format_guardian_summary(
        [{"type": "xp", "value": 10}], state, "sv", mech=_mech(xp=10),
    )
    assert "[COMBAT:" not in out


# ══ Trunkerings-reparation i live _parse_json (§4) ══════════════════════

def test_parse_json_repairs_truncated_mid_string():
    raw = '{"xp": 150, "logbook": "Vi vilade vid läger'  # kapad mitt i strängen
    result = guardian._parse_json(raw)
    assert result is not None
    assert result["xp"] == 150


def test_parse_json_repairs_truncated_nested_list():
    raw = '{"items_add": [{"name": "Svärd", "qty": 1}, {"name": "Rep"'
    result = guardian._parse_json(raw)
    assert result is not None
    assert len(result["items_add"]) == 2
    assert result["items_add"][1]["name"] == "Rep"


def test_parse_json_repairs_truncated_with_prose_prefix():
    raw = 'Här är mekaniken:\n```json\n{"xp": 50, "damage": [{"target": "player", "amount": 4'
    result = guardian._parse_json(raw)
    assert result is not None
    assert result["xp"] == 50


def test_parse_json_valid_json_unchanged():
    raw = '{"xp": 50, "damage": []}'
    result = guardian._parse_json(raw)
    assert result == {"xp": 50, "damage": []}


def test_parse_json_garbage_returns_none():
    assert guardian._parse_json("inget json alls, bara text") is None


def test_repair_truncated_json_helper_direct():
    assert guardian._repair_truncated_json('{"a": 1}') == '{"a": 1}'
    fixed = guardian._repair_truncated_json('{"a": "kapad sträng')
    assert fixed is not None and json.loads(fixed)["a"] == "kapad sträng"
    assert guardian._repair_truncated_json("") is None


# ══ Död Battle AI borttagen (§6) ════════════════════════════════════════

def test_battle_ai_deleted_from_guardian():
    for name in ("battle_ai_decide", "apply_enemy_actions", "_fallback_enemy_actions",
                 "BATTLE_AI_SYSTEM", "BATTLE_AI_SYSTEM_EN"):
        assert not hasattr(guardian, name), f"{name} ska vara borttagen (0 anropare)"


def test_apply_level_up_bonuses_importable_for_main():
    """main.py (sibling) importerar _apply_level_up_bonuses — måste finnas och fungera."""
    from guardian import _apply_level_up_bonuses
    ch = {"name": "T", "class": "Fighter", "level": 2,
          "hp": {"current": 10, "max": 10, "temp": 0},
          "abilities": {"CON": {"score": 14, "mod": 2}}}
    effects = []
    _apply_level_up_bonuses(ch, effects)
    assert any(e["type"] == "level_up" for e in effects)
    assert ch["hp"]["max"] == 17  # 10 + (10//2 + 2)


# ══ Level-up-konsolidering (§5) ═════════════════════════════════════════

def test_level_up_multi_level_while_loop():
    state = _make_state()
    state["character"]["level"] = 2
    state["character"]["xp"] = {"current": 0, "next_level": 900}
    effects = guardian.apply_mechanics(state, _mech(xp=3000), skip_effects=[])
    ch = state["character"]
    # 3000 ≥ 900 (L2→3) ≥ 2700 (L3→4) — while-loop tar alla nivåer på en tur
    assert ch["level"] == 4
    assert ch["xp"]["next_level"] == 6500
    assert sum(1 for e in effects if e["type"] == "level_up") == 2


def test_level_up_runs_even_with_zero_xp_gain():
    """Karaktär redan över tröskeln (XP via tagg-vägen) + xp_gain=0 → level-up ändå.
    3100 ≥ 900 (L2→3) OCH ≥ 2700 (L3→4) — while-motorn catchar upp båda."""
    state = _make_state()
    state["character"]["level"] = 2
    state["character"]["xp"] = {"current": 3100, "next_level": 2700}
    guardian.apply_mechanics(state, _mech(xp=0), skip_effects=[])
    ch = state["character"]
    assert ch["level"] == 4
    assert ch["xp"]["next_level"] == 6500


def test_level_up_skipped_when_xp_came_via_skip_tag():
    """[XP:]-tagg-dedup: samma XP appliceras inte två gånger."""
    state = _make_state()
    state["character"]["xp"] = {"current": 0, "next_level": 300}
    effects = guardian.apply_mechanics(state, _mech(xp=100), skip_effects=[("xp", "100")])
    assert state["character"]["xp"]["current"] == 0
    assert not any(e["type"] == "xp" for e in effects)


def test_level_up_quest_reward_while_loop():
    state = _make_state()
    state["character"]["level"] = 1
    state["character"]["xp"] = {"current": 0, "next_level": 300}
    state["quests"] = [{"id": "q1", "name": "Rädda byn", "status": "aktiv",
                        "xp_reward": 3000, "gold_reward": 0}]
    guardian.apply_mechanics(state, _mech(quests_completed=["Rädda byn"]), skip_effects=[])
    ch = state["character"]
    assert ch["xp"]["current"] == 3000
    assert ch["level"] == 4  # 300→2, 900→3, 2700→4 (while, inte if)
    assert ch["xp"]["next_level"] == 6500


def test_xp_next_level_from_thresholds_not_900():
    """xp-dict saknas helt för level 5 → next_level = _XP_THRESHOLDS[5] = 14000."""
    state = _make_state()
    state["character"]["level"] = 5
    state["character"].pop("xp", None)
    guardian.apply_mechanics(state, _mech(xp=0), skip_effects=[])
    assert state["character"]["xp"]["next_level"] == 14000


# ══ format_guardian_summary — nya renderingsfall (§4c) ══════════════════

def _summary(effects, mech=None, lang="sv", state=None):
    return guardian.format_guardian_summary(
        effects, state or _make_state(), lang, mech=mech or _mech(),
    )


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_spell_slots_spend_rendered(lang):
    state = _make_state()
    state["character"]["spell_slots"] = {"current": 1, "max": 4}
    out = _summary([{"type": "spell_slots_spend", "name": "Eldklot", "level": 3, "remaining": 1}], lang=lang, state=state)
    assert "Eldklot" in out
    assert "1/4" in out


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_spell_slots_blocked_rendered(lang):
    state = _make_state()
    state["character"]["spell_slots"] = {"current": 0, "max": 2}
    out = _summary([{"type": "spell_slots_blocked", "name": "Eldklot", "level": 3}], lang=lang, state=state)
    assert "Eldklot" in out
    assert "⛔" in out
    assert "0/2" in out


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_inspiration_rendered(lang):
    gain = _summary([{"type": "inspiration_gain"}], lang=lang)
    spend = _summary([{"type": "inspiration_spend"}], lang=lang)
    assert "✨" in gain and gain != ""
    assert "✨" in spend and spend != ""
    if lang == "sv":
        assert "erhållen" in gain and "spenderad" in spend
    else:
        assert "gained" in gain and "spent" in spend


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_exhaustion_rendered(lang):
    out = _summary([{"type": "exhaustion", "level": 2}], lang=lang)
    assert "2/6" in out
    out_rest = _summary([{"type": "exhaustion", "level": 1, "source": "long_rest"}], lang=lang)
    assert "1/6" in out_rest
    if lang == "sv":
        assert "Utmattning" in out and "lång vila" in out_rest
    else:
        assert "Exhaustion" in out and "long rest" in out_rest


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_exhaustion_hp_halved_and_recovered(lang):
    out = _summary([{"type": "exhaustion_hp_halved", "max": 7}], lang=lang)
    assert "7" in out and "🥀" in out
    out2 = _summary([{"type": "exhaustion_recovered", "max": 14}], lang=lang)
    assert "14" in out2 and "🍃" in out2


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_spell_add_rendered(lang):
    out = _summary([{"type": "spell_add", "value": "Magisk hand", "level": 0}], lang=lang)
    assert "Magisk hand" in out
    assert "📜" in out


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_rest_rendered(lang):
    long_out = _summary([], mech=_mech(rest={"kind": "long"}), lang=lang)
    assert ("Lång vila" in long_out) if lang == "sv" else ("Long rest" in long_out)
    short_out = _summary(
        [{"type": "vila", "value": 8, "detail": "+3 HP (1d8+2)"}],
        mech=_mech(rest={"kind": "short"}), lang=lang,
    )
    assert "Kort vila" in short_out if lang == "sv" else "Short rest" in short_out
    assert "+3 HP" in short_out
    assert short_out.count("vila" if lang == "sv" else "rest") >= 1  # ingen dubbel-rad


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_training_rendered(lang):
    prog = _summary([{"type": "training_progress", "name": "Athletics", "days": 4}], lang=lang)
    assert "Athletics" in prog and "4" in prog
    done = _summary([{"type": "training_complete", "skill": "Athletics"}], lang=lang)
    assert "Athletics" in done
    assert "🎓" in prog and "🎓" in done


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_cover_set_rendered(lang):
    out = _summary([{"type": "cover_set", "cover": "half"}], lang=lang)
    assert "+2" in out
    full = _summary([{"type": "cover_set", "cover": "full"}], lang=lang)
    assert full != "" and "🧱" in full
    none_cov = _summary([{"type": "cover_set", "cover": None}], lang=lang)
    assert none_cov != ""


@pytest.mark.parametrize("lang", ["sv", "en"])
def test_summary_npc_near_rendered(lang):
    out = _summary([{"type": "npc_near", "value": "Mimmrick → nära"}], lang=lang)
    assert "Mimmrick" in out and "👥" in out
