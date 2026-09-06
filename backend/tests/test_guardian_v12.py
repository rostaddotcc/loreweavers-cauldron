"""v1.2 'The Honest Dice' — guardian-side regression tests (parent take-over wave 4).

Täcker: motorrullad spelarskada, status_apply live, valutavägran, AC vid equip,
proficiency-skala, initiative key-fix, quest-guld dedup, lång vila halva HD.
"""
import guardian


def _state(**ch_extra):
    ch = {"name": "Aria", "level": 1, "hp": {"current": 20, "max": 20},
          "ac": 12, "proficiency": 2,
          "abilities": {"STR": {"score": 10, "mod": 0}, "DEX": {"score": 14, "mod": 2},
                        "CON": {"score": 12, "mod": 1}}}
    ch.update(ch_extra)
    return {"character": ch, "inventory": [], "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
            "quests": [], "npcs": [], "world": {"combat": None}, "meta": {"turn_count": 1}}


def _combat_state(enemies=None, allies=None, active=True):
    st = _state()
    st["world"]["combat"] = {
        "active": active, "round": 1, "enemies": enemies or [],
        "allies": allies or [], "log": [], "turn_order": [], "initiative": [],
    }
    return st


# ── motorrullad spelarskada ──────────────────────────────────────────────

def test_player_damage_rolled_from_weapon_dice():
    st = _combat_state(enemies=[{"name": "Goblin", "hp": 40, "max_hp": 40, "ac": 12, "alive": True}])
    st["inventory"] = [{"name": "Långsvärd", "type": "Vapen", "category": "weapon",
                        "damage_dice": "1d8", "damage_type": "slashing", "equipped": True,
                        "weight": 3.0, "qty": 1}]
    mech = {"player_attacks": [{"target": "Goblin", "hit": True, "damage": 999, "crit": False}]}
    guardian.apply_mechanics(st, mech)
    e = st["world"]["combat"]["enemies"][0]
    # LLM-värdet 999 IGNORERAS — 1d8 ger 1–8 (+ ev. DEX? nej: damage_dice bara)
    assert 1 <= 40 - e["hp"] <= 8, f"skada utanför 1d8: {40 - e['hp']}"


def test_player_damage_crit_doubles_dice():
    st = _combat_state(enemies=[{"name": "Orc", "hp": 60, "max_hp": 60, "ac": 12, "alive": True}])
    st["inventory"] = [{"name": "Yxa", "type": "Vapen", "category": "weapon",
                        "damage_dice": "1d6", "damage_type": "slashing", "equipped": True,
                        "weight": 1.0, "qty": 1}]
    mech = {"player_attacks": [{"target": "Orc", "hit": True, "damage": 3, "crit": True}]}
    guardian.apply_mechanics(st, mech)
    e = st["world"]["combat"]["enemies"][0]
    dmg = 60 - e["hp"]
    assert 2 <= dmg <= 12, f"crit 2d6 utanför intervall: {dmg}"


def test_player_damage_falls_back_to_llm_without_weapon():
    st = _combat_state(enemies=[{"name": "Ghost", "hp": 40, "max_hp": 40, "ac": 12, "alive": True}])
    mech = {"player_attacks": [{"target": "Ghost", "hit": True, "damage": 7, "crit": False}]}
    guardian.apply_mechanics(st, mech)
    assert st["world"]["combat"]["enemies"][0]["hp"] == 33


# ── status_apply live ────────────────────────────────────────────────────

def test_status_apply_restrains_enemy_and_shows_effect():
    st = _combat_state(enemies=[{"name": "Goblin", "hp": 9, "max_hp": 9, "ac": 12, "alive": True}])
    mech = {"status_apply": [{"name": "restrain", "target": "goblin", "duration": 2}]}
    effects = guardian.apply_mechanics(st, mech)
    e = st["world"]["combat"]["enemies"][0]
    assert any(s.get("name") == "restrain" for s in e.get("statuses", []))
    assert any(x["type"] == "status" for x in effects)
    # motorn: restrained fiende → attack_disadvantage True i combat-hjälpen
    from combat import has_disadvantage
    assert has_disadvantage(e)


def test_status_apply_player_poison():
    st = _combat_state(enemies=[])
    st["world"]["combat"] = {"active": True, "round": 1, "enemies": [], "allies": [],
                             "log": [], "turn_order": [], "initiative": []}
    mech = {"status_apply": [{"name": "poison", "target": "player", "duration": 1}]}
    guardian.apply_mechanics(st, mech)
    assert any(s.get("name") == "poison" for s in st["character"].get("statuses", []))


# ── valuta: vägra i stället för förinta ──────────────────────────────────

def test_currency_refusal_preserves_coins():
    st = _state()
    st["currency"]["gp"] = 5
    mech = {"currency": [{"denom": "gp", "amount": -10}]}
    effects = guardian.apply_mechanics(st, mech)
    assert st["currency"]["gp"] == 5, "mynt förstörda — clamp tillbaka?"
    assert any(x["type"] == "guld_fail" for x in effects)


def test_currency_sufficient_spend_ok():
    st = _state()
    st["currency"]["gp"] = 30
    guardian.apply_mechanics(st, {"currency": [{"denom": "gp", "amount": -10}]})
    assert st["currency"]["gp"] == 20


# ── AC följer rustning ───────────────────────────────────────────────────

def test_ac_recomputes_on_armor_equipped():
    st = _combat_state()  # har character + inventory[]
    st["character"]["ac"] = 12
    mech = {"items_add": [{"name": "Kedjerustning", "type": "Rustning", "category": "armor",
                           "ac_bonus": 16, "equipped": True, "weight": 25.0, "qty": 1}]}
    guardian.apply_mechanics(st, mech)
    # chain (16≥14) →DEX kapad 0 → AC 16
    assert st["character"]["ac"] == 16
    assert st["character"]["ac_source"].startswith("equipped:")


# ── proficiency + vila ───────────────────────────────────────────────────

def test_proficiency_scales_at_level5():
    ch = {"name": "Aria", "level": 1, "hp": {"current": 20, "max": 20}, "proficiency": 2,
          "class": "Roguish", "abilities": {"CON": {"score": 12, "mod": 1}},
          "hit_dice": {"total": 1, "remaining": 1, "dice": "1d8"},
          "spell_slots": {"current": 0, "max": 0}}
    guardian._apply_level_up_bonuses(ch, [])
    ch["level"] = 5
    guardian._apply_level_up_bonuses(ch, [])
    assert ch["proficiency"] == 3, f"proficiency vid lvl5: {ch['proficiency']}"


def test_long_rest_restores_half_hit_dice():
    st = _state()
    st["character"]["hp"]["current"] = 5
    st["character"]["hit_dice"] = {"total": 6, "remaining": 0, "dice": "1d8"}
    st["character"]["spell_slots"] = {"current": 0, "max": 4}
    guardian.apply_mechanics(st, {"rest": {"kind": "long"}})
    hd = st["character"]["hit_dice"]
    assert hd["remaining"] == 3, f"halva av 6 förväntades, fick {hd['remaining']}"
    assert st["character"]["spell_slots"]["current"] == 4
    assert st["character"]["hp"]["current"] == 20


# ── initiative key-fix ───────────────────────────────────────────────────

def test_initiative_player_name_keeps_player_key():
    st = _combat_state(enemies=[{"name": "Goblin", "hp": 9, "max_hp": 9, "ac": 12, "alive": True}])
    mech = {"initiative_entries": [{"name": "Aria", "value": 17},
                                   {"name": "Goblin", "value": 8}]}
    guardian.apply_mechanics(st, mech)
    init = st["world"]["combat"]["initiative"]
    aria = next(e for e in init if e["name"] == "Aria")
    assert aria["key"] == "player", f"spelaren fick key {aria['key']}"


# ── quest-guld dedup ─────────────────────────────────────────────────────

def test_quest_gold_deduped_vs_tag_payment():
    st = _state()
    st["quests"] = [{"id": "q1", "name": "Lyktans Hemlighet", "description": "d",
                     "status": "aktiv", "xp_reward": 0, "gold_reward": 50}]
    # skip_effects = [GULD:]-taggen applicerade redan 50 gp DÖRE guardian (saldo höjt)
    st["meta"]["last_effects"] = [{"type": "guld", "value": 50, "denom": "gp"}]
    st["currency"]["gp"] = 50
    st["character"]["xp"] = {"current": 0, "next_level": 300}
    guardian.apply_mechanics(st, {"quests_completed": [{"name": "Lyktans Hemlighet"}]},
                             skip_effects=st["meta"]["last_effects"])
    assert st["currency"]["gp"] == 50, f"dubbelbetalning: {st['currency']['gp']} gp"
