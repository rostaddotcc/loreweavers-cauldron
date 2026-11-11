"""P1b ENGINE — flykt/jaktklocka (§2) + status-expiry-motorn (§3).

LLM-fria tester: apply_mechanics / combat.* anropas direkt med handskrivna
mech-dicts. Fixtures innehåller DUBLETTNAMN (3× "Archival Sentinel") — stående
projektregel sedan 2026-09-13 — och äldre states utan de nya fälten tolereras.
Sparprov rullas via rng-sömen (enemy_rolls-mönstet: StubRng.randbelow).

NOT (denna rundas scope): [FLYKT:]/[STATUS:]-regex-taggarna i main.py och
[Resultat: FLYKT/…SPAR]-grenarna är DELIBERAT försenade till nästa runda
(main.py ägs av en annan agent denna round) — dessa tester täcker Guardian-
vägen + motorn.
"""
import guardian
import combat


class StubRng:
    """Deterministisk rng-söm: randbelow(n) → första kvarvärdet (d20 = v+1)."""

    def __init__(self, values):
        self.values = list(values)

    def randbelow(self, n):
        return self.values.pop(0) if self.values else 1


def _state(**ch_extra):
    ch = {"name": "Aria", "level": 1, "hp": {"current": 20, "max": 20},
          "ac": 12, "proficiency": 2,
          "abilities": {"STR": {"score": 10, "mod": 0}, "DEX": {"score": 14, "mod": 2},
                        "CON": {"score": 12, "mod": 1}}}
    ch.update(ch_extra)
    return {"character": ch, "inventory": [], "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
            "quests": [], "npcs": [], "world": {"combat": None}, "meta": {"turn_count": 1}}


def _enemy(name, i, hp=12, **extra):
    e = {"id": i, "name": name, "hp": hp, "max_hp": hp, "ac": 12, "alive": True,
         "statuses": [], "attack_bonus": 3, "damage_dice": "1d6+1"}
    e.update(extra)
    return e


def _dupes(hp=12):
    """3× samma namn — Name#id-rotationen måste hålla (§1.1/§4.2)."""
    return [_enemy("Archival Sentinel", i, hp=hp) for i in range(3)]


def _combat_state(enemies=None, active=True):
    st = _state()
    st["world"]["combat"] = {
        "active": active, "round": 1, "enemies": enemies or [], "allies": [],
        "log": [], "turn_order": [], "initiative": [],
    }
    return st


# ═══════════════════════════════════════
# 1. Flykt / jakt — 3/3-klockan (§2.2)
# ═══════════════════════════════════════

def test_flee_declared_starts_player_chase():
    st = _combat_state(_dupes())
    fx = guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    c = st["world"]["combat"]
    assert c["chase"]["active"] is True
    assert c["chase"]["mode"] == "player_flee" and c["chase"]["quarry"] == "player"
    assert c["chase"]["successes"] == 0 and c["chase"]["failures"] == 0
    assert c["chase"]["target"] == 3
    assert any(e["type"] == "chase_start" for e in fx)


def test_flee_declared_enemy_quarry_name_id_key():
    """Dublettnamn: bytet får Name#id-nyckel, lägsta id:t vinner (§2.2)."""
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "Archival Sentinel"}})
    c = st["world"]["combat"]
    assert c["chase"]["mode"] == "enemy_flee"
    assert c["chase"]["quarry"] == "Archival Sentinel#0"


def test_flee_double_start_guard():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    assert not any(e["type"] == "chase_start" for e in fx)
    assert st["world"]["combat"]["chase"]["rounds"] == 0  # ingen omstart


def test_flee_requires_active_combat():
    st = _combat_state(_dupes(), active=False)
    fx = guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    assert not any(e["type"] == "chase_start" for e in fx)
    assert not st["world"]["combat"].get("chase")


def test_flee_unknown_target_ignored():
    st = _combat_state(_dupes())
    fx = guardian.apply_mechanics(st, {"flee_declared": {"target": "nobody-here"}})
    assert not any(e["type"] == "chase_start" for e in fx)
    assert not st["world"]["combat"].get("chase")


def test_flee_zero_hp_player_cannot_flee():
    st = _combat_state(_dupes())
    st["character"]["hp"]["current"] = 0
    fx = guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    assert not any(e["type"] == "chase_start" for e in fx)


def test_chase_three_successes_escape_ends_combat():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = []
    for _ in range(3):
        fx += guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "escape"}]})
    c = st["world"]["combat"]
    assert c["chase"]["successes"] == 3 and c["chase"]["result"] == "escaped"
    assert c["active"] is False
    ends = [e for e in fx if e["type"] == "combat_end"]
    assert len(ends) == 1 and ends[0]["value"] == "player fled"
    assert c["ended_turn"] == 1


def test_chase_three_failures_caught_combat_continues():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = []
    for _ in range(3):
        fx += guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "caught"}]})
    c = st["world"]["combat"]
    assert c["chase"]["failures"] == 3 and c["chase"]["result"] == "caught"
    assert c["chase"]["active"] is False
    assert c["active"] is True  # striden går vidare
    assert c["caught_side"] == "player"  # engångsfördel för förföljaren
    assert not any(e["type"] == "combat_end" for e in fx)


def test_chase_enemy_flee_escape_ends_with_enemies_fled():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "Archival Sentinel"}})
    fx = []
    for _ in range(3):
        fx += guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "escape"}]})
    ends = [e for e in fx if e["type"] == "combat_end"]
    assert len(ends) == 1 and ends[0]["value"] == "enemies fled"


def test_chase_cap_tie_escapes_with_gold_cost():
    """6 rundor, 3/3 = oavgjort → bytet undkommer MED kostnad (halva guldet)."""
    st = _combat_state(_dupes())
    st["currency"]["gp"] = 10
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = []
    for out in ("escape", "caught", "escape", "caught", "stalemate", "stalemate"):
        fx += guardian.apply_mechanics(st, {"chase_progress": [{"outcome": out}]})
    assert st["currency"]["gp"] == 5
    costs = [e for e in fx if e["type"] == "chase_escape_cost"]
    assert len(costs) == 1 and costs[0]["value"] == 5
    assert st["world"]["combat"]["active"] is False
    assert any(e["type"] == "combat_end" and e["value"] == "player fled" for e in fx)


def test_chase_stalemate_never_completes_before_cap():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = []
    for _ in range(5):
        fx += guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "stalemate"}]})
    c = st["world"]["combat"]
    assert c["chase"]["active"] is True
    assert c["chase"]["successes"] == 0 and c["chase"]["failures"] == 0
    assert not any(e["type"] == "combat_end" for e in fx)


def test_end_combat_double_end_guard():
    st = _combat_state(_dupes())
    c = st["world"]["combat"]
    fx = []
    assert guardian._end_combat(st, "player fled", fx) is True
    assert guardian._end_combat(st, "player fled", fx) is False
    assert len([e for e in fx if e["type"] == "combat_end"]) == 1
    assert c["ended_turn"] == 1  # satts exakt en gång


def test_chase_tick_noop_after_end():
    """Klockan är död efter slutet — inga fler ticks, inga dubbel-sut."""
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    for _ in range(3):
        guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "escape"}]})
    fx = guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "escape"}]})
    assert not any(e["type"] == "chase_tick" for e in fx)
    assert len([e for e in fx if e["type"] == "combat_end"]) == 0


def test_chase_progress_bad_outcome_dropped():
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"flee_declared": {"target": "player"}})
    fx = guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "teleport"}]})
    assert not any(e["type"] == "chase_tick" for e in fx)
    assert st["world"]["combat"]["chase"]["rounds"] == 0


# ═══════════════════════════════════════
# 2. Status-motorn — refresh-not-stack + expiry-tick (§3)
# ═══════════════════════════════════════

def test_status_apply_regressions_unwire():
    """UN-WIRE-regressionen: mech['status_apply'] MÅSTE skapa statusar."""
    st = _combat_state(_dupes())
    guardian.apply_mechanics(st, {"status_apply": [
        {"name": "poison", "target": "Archival Sentinel", "duration": 2, "save_dc": 12}]})
    for e in st["world"]["combat"]["enemies"]:
        assert any(s["name"] == "poison" for s in e["statuses"]), \
            f"status_apply konsumerades inte på {e['name']}#{e['id']}"


def test_status_apply_refresh_not_stack():
    st = _combat_state([_enemy("Goblin", 0)])
    guardian.apply_mechanics(st, {"status_apply": [
        {"name": "poison", "target": "Goblin", "duration": 2, "save_dc": 10}]})
    guardian.apply_mechanics(st, {"status_apply": [
        {"name": "poison", "target": "Goblin", "duration": 5, "save_dc": 15}]})
    sts = [s for s in st["world"]["combat"]["enemies"][0]["statuses"] if s["name"] == "poison"]
    assert len(sts) == 1, "status staplades — refresh-not-stack (§3.1.5)"
    assert sts[0]["duration"] == 5          # max av gammalt och nytt
    assert sts[0]["dmg_per_turn"] == 2      # en enda DoT
    assert sts[0]["save_dc"] == 15          # högre DC lyfter (värsta-fallet)


def test_status_apply_lower_save_dc_keeps_worst_case():
    st = _combat_state([_enemy("Goblin", 0)])
    guardian.apply_mechanics(st, {"status_apply": [
        {"name": "restrain", "target": "Goblin", "duration": 2, "save_dc": 15}]})
    guardian.apply_mechanics(st, {"status_apply": [
        {"name": "restrain", "target": "Goblin", "duration": 2, "save_dc": 10}]})
    assert st["world"]["combat"]["enemies"][0]["statuses"][0]["save_dc"] == 15


def test_status_apply_dedup_key_skips_tag_path():
    """§4.3: [STATUS:]-vägen la nyckeln i skip_effects → Guardian-hoppar."""
    st = _combat_state([_enemy("Goblin", 0)])
    fx = guardian.apply_mechanics(
        st, {"status_apply": [{"name": "burn", "target": "Goblin", "duration": 3}]},
        skip_effects=[("status_apply", "burn:goblin")])
    assert not any(e["type"] == "status" for e in fx)
    assert not st["world"]["combat"]["enemies"][0]["statuses"]


def test_status_apply_unknown_name_dropped_no_raise():
    st = _combat_state([_enemy("Goblin", 0)])
    fx = guardian.apply_mechanics(st, {"status_apply": [
        {"name": "deathray", "target": "Goblin", "duration": 2},
        {"name": "stun", "target": "Goblin", "duration": 2}]})
    g = st["world"]["combat"]["enemies"][0]
    assert [s["name"] for s in g["statuses"]] == ["stun"]
    assert sum(1 for e in fx if e["type"] == "status") == 1


def test_status_tick_once_per_round():
    st = _combat_state([_enemy("Goblin", 0, hp=20)])
    c = st["world"]["combat"]
    combat.add_status(c["enemies"][0], "poison", duration=3)
    combat._tick_all_statuses(st, c)
    assert c["enemies"][0]["hp"] == 18          # 2 poison-skada
    fx2 = combat._tick_all_statuses(st, c)      # SAMMA runda → no-op
    assert c["enemies"][0]["hp"] == 18 and fx2 == []
    assert c["_statuses_ticked_round"] == 1
    c["round"] = 2
    combat._tick_all_statuses(st, c)
    assert c["enemies"][0]["hp"] == 16


def test_status_expiry_emits_status_end():
    st = _combat_state([_enemy("Goblin", 0)])
    c = st["world"]["combat"]
    combat.add_status(c["enemies"][0], "prone", duration=1)
    fx = combat._tick_all_statuses(st, c)
    assert not c["enemies"][0]["statuses"]
    assert any(e["type"] == "status_end" and e.get("status") == "prone" for e in fx)


def test_status_tick_respects_resistance():
    st = _combat_state([_enemy("Goblin", 0, hp=20, resistances=["poison"])])
    c = st["world"]["combat"]
    combat.add_status(c["enemies"][0], "poison", duration=2)
    fx = combat._tick_all_statuses(st, c)
    # poison 2 × 0.5 (resist) = 1 → hp 19
    assert c["enemies"][0]["hp"] == 19
    assert any(e["type"] in ("status_dmg", "status_resisted") for e in fx)


# ═══════════════════════════════════════
# 3. Sparprov — server-rullade via rng-söm (§3.1.4)
# ═══════════════════════════════════════

def test_enemy_save_success_removes_status():
    st = _combat_state([_enemy("Goblin", 0)])
    c = st["world"]["combat"]
    combat.add_status(c["enemies"][0], "poison", duration=3, save_dc=10)
    fx = combat._tick_all_statuses(st, c, rng=StubRng([12]))   # d20=13 ≥ 10
    assert not c["enemies"][0]["statuses"]
    sv = [e for e in fx if e["type"] == "status_save"]
    assert len(sv) == 1 and sv[0]["success"] and sv[0]["d20"] == 13 and sv[0]["dc"] == 10
    assert any(e["type"] == "status_end" for e in fx)
    assert any("breaks free" in x.get("text", "") for x in c["log"])


def test_enemy_save_fail_keeps_status():
    st = _combat_state([_enemy("Goblin", 0)])
    c = st["world"]["combat"]
    combat.add_status(c["enemies"][0], "poison", duration=3, save_dc=15)
    fx = combat._tick_all_statuses(st, c, rng=StubRng([3]))    # d20=4 < 15
    g = c["enemies"][0]
    assert [s["name"] for s in g["statuses"]] == ["poison"]
    assert g["statuses"][0]["duration"] == 2    # ticken drog ändå av duration
    assert any(e["type"] == "status_save" and not e["success"] for e in fx)


def test_player_save_surfaces_request_not_roll():
    st = _combat_state([])
    st["character"]["statuses"] = [{"name": "poison", "duration": 2,
                                   "dmg_per_turn": 0, "save_dc": 12}]
    fx = combat._tick_all_statuses(st, st["world"]["combat"])
    req = [e for e in fx if e["type"] == "status_save_request"]
    assert len(req) == 1 and req[0]["dc"] == 12 and req[0]["target"] == "player"
    assert not any(e["type"] == "status_save" for e in fx)  # ingen server-roll
    assert any(s["name"] == "poison" for s in st["character"]["statuses"])


def test_status_save_success_removes_player_status():
    st = _combat_state(_dupes())
    st["character"]["statuses"] = [{"name": "poison", "duration": 2,
                                   "dmg_per_turn": 2, "save_dc": 12}]
    fx = guardian.apply_mechanics(st, {"status_save": [
        {"target": "player", "name": "poison", "success": True}]})
    assert not st["character"]["statuses"]
    assert any(e["type"] == "status_end" for e in fx)
    assert any(e["type"] == "status_save" and e["success"] for e in fx)


def test_status_save_failure_keeps_status():
    st = _combat_state(_dupes())
    st["character"]["statuses"] = [{"name": "poison", "duration": 2,
                                   "dmg_per_turn": 2, "save_dc": 12}]
    fx = guardian.apply_mechanics(st, {"status_save": [
        {"target": "player", "name": "poison", "success": False}]})
    assert st["character"]["statuses"] != []
    assert not any(e["type"] == "status_end" for e in fx)


def test_status_save_dedup_respects_resultat_key():
    """§4.3: [Resultat:]-vägen la ("status_save", "poison:player") → hoppa."""
    st = _combat_state(_dupes())
    st["character"]["statuses"] = [{"name": "poison", "duration": 2,
                                   "dmg_per_turn": 2, "save_dc": 12}]
    fx = guardian.apply_mechanics(
        st, {"status_save": [{"target": "player", "name": "poison", "success": True}]},
        skip_effects=[("status_save", "poison:player")])
    assert not any(e["type"] == "status_save" for e in fx)
    assert st["character"]["statuses"] != []   # orörd — tagg-vägen ägde provet


def test_status_save_without_matching_status_dropped():
    st = _combat_state(_dupes())
    fx = guardian.apply_mechanics(st, {"status_save": [
        {"target": "player", "name": "charm", "success": True}]})
    assert not any(e["type"] in ("status_save", "status_end") for e in fx)


# ═══════════════════════════════════════
# 4. Extraktionsvalidering (_sanitize) — droppa aldrig-raise (§4.1)
# ═══════════════════════════════════════

def test_sanitize_status_apply_enum_and_clamps():
    mech = {"status_apply": [
        {"name": "poison", "target": "Goblin", "duration": 99, "save_dc": 40},
        {"name": "stun", "target": "Goblin", "duration": 0},
        {"name": "deathray", "target": "Goblin", "duration": 2},
        "not-a-dict",
        {"name": "poison", "target": "", "duration": 2},
        {"name": "poison", "target": "Goblin", "duration": "x", "save_dc": "y"},
    ]}
    out = guardian._sanitize_mechanics(mech)
    cleaned = out["status_apply"]
    assert len(cleaned) == 3
    assert cleaned[0] == {"name": "poison", "target": "Goblin", "duration": 10, "save_dc": 25}
    assert cleaned[1] == {"name": "stun", "target": "Goblin", "duration": 1, "save_dc": None}
    assert cleaned[2] == {"name": "poison", "target": "Goblin", "duration": 2, "save_dc": None}


def test_sanitize_flee_declared_dict_or_null():
    assert guardian._sanitize_mechanics({"flee_declared": "player"})["flee_declared"] is None
    assert guardian._sanitize_mechanics({"flee_declared": {"target": "  "}})["flee_declared"] is None
    assert guardian._sanitize_mechanics(
        {"flee_declared": {"target": " goblin "}})["flee_declared"] == {"target": "goblin"}
    assert guardian._sanitize_mechanics({"flee_declared": None})["flee_declared"] is None


def test_sanitize_chase_progress_enum_and_max_one():
    out = guardian._sanitize_mechanics({"chase_progress": [
        {"outcome": "nope"}, {"outcome": "ESCAPE"}, {"outcome": "caught"}]})
    assert out["chase_progress"] == [{"outcome": "escape"}]


def test_sanitize_status_save_bool_strict():
    out = guardian._sanitize_mechanics({"status_save": [
        {"target": "player", "name": "poison", "success": "yes"},
        {"target": "", "name": "x", "success": True},
        {"target": "player", "name": "BURN", "success": False}]})
    assert out["status_save"] == [{"target": "player", "name": "burn", "success": False}]


def test_old_state_without_new_fields_tolerated():
    """Äldre states (inga statuses/chase-fält) → defaults, ingen KeyError."""
    st = _combat_state([{"id": 0, "name": "Rust-Husk", "hp": 10, "max_hp": 10,
                         "ac": 12, "alive": True}])  # inga statuses/morale-fält
    fx = guardian.apply_mechanics(st, {"chase_progress": [{"outcome": "escape"}],
                                       "status_save": [{"target": "player", "name": "poison", "success": True}],
                                       "flee_declared": {"target": "Rust-Husk"}})
    c = st["world"]["combat"]
    assert c["chase"]["quarry"] == "Rust-Husk#0"


# ═══════════════════════════════════════
# 5. Prompt-kontrakt (fälten måste läras ut)
# ═══════════════════════════════════════

def test_guardian_prompt_teaches_p1b_fields():
    g = guardian.GUARDIAN_POST_SYSTEM
    for token in ("flee_declared", "chase_progress", "status_save", "save_dc"):
        assert token in g, f"{token} saknas i GUARDIAN_POST_SYSTEM"
    assert '"flee_declared": null' in g and '"status_save": []' in g
