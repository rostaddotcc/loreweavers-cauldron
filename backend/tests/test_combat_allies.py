"""Tester för allierade (vänliga NPC:er) i stridsmotorn.

Täcker:
  - combat.add_allies — normalisering + append till aktiv strid
  - combat.roll_initiative — ally-{id}-nycklar i turordningen
  - combat.ally_turn — skada på fiende + combat_log med actor "ally"
  - combat.advance_turn — rotation genom ally-slots (och hopp över döda)
  - guardian.apply_mechanics — ally_attacks/ally_damage
  - main._parse_allierad_tag — [ALLIERAD:]-taggen
  - ally-död → alive=false
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import combat
import guardian


def _make_state() -> dict:
    """Minimal spelstate med karaktär + tom world."""
    return {
        "meta": {"turn_count": 1},
        "character": {
            "name": "Kael",
            "hp": {"current": 20, "max": 20, "temp": 0},
            "ac": 15,
            "initiative": 2,
        },
        "world": {},
    }


def _start_combat(state: dict) -> dict:
    """Öppna en strid mot en goblin."""
    return combat.start_combat(state, [
        {"name": "Goblin", "hp": 7, "ac": 12, "attack_bonus": 4, "damage_dice": "1d6+2"},
    ])


def _ally_mech(**overrides) -> dict:
    """Minimal mech-dict med ally-fälten (och tomma övriga stridsfält)."""
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


# ── add_allies ──────────────────────────────────────────────────────────

def test_add_allies_normalizes_and_appends():
    state = _make_state()
    c = _start_combat(state)
    assert c["allies"] == []

    combat.add_allies(state, [
        {"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 4, "damage_dice": "1d6+2"},
        {"name": "Tord", "hp": 9, "ac": 12},
    ])

    allies = state["world"]["combat"]["allies"]
    assert len(allies) == 2
    a = allies[0]
    assert a["id"] == 0
    assert a["name"] == "Mimmrick"
    assert a["hp"] == 12 and a["max_hp"] == 12
    assert a["ac"] == 14
    assert a["alive"] is True
    assert a["statuses"] == []
    assert a["attack_bonus"] == 4
    assert a["damage_dice"] == "1d6+2"
    assert a["actions_remaining"] == 1
    # Defaultvärden för Tord
    assert allies[1]["id"] == 1
    assert allies[1]["ac"] == 12
    assert allies[1]["attack_bonus"] == 3
    assert allies[1]["damage_dice"] == "1d6+1"


def test_add_allies_ignored_without_active_combat():
    state = _make_state()
    result = combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14}])
    assert result == {}
    assert "combat" not in state.get("world", {})


def test_add_allies_joins_existing_turn_order(monkeypatch):
    """Allierade ska få egna turer direkt — insorterade på initiativ utan
    att current_index flyttas till en annan combatant."""
    state = _make_state()
    c = _start_combat(state)
    c["turn_order"] = [
        {"key": "player", "name": "Kael", "initiative": 20, "acted": False},
        {"key": "enemy:0", "name": "Goblin", "initiative": 10, "acted": False},
    ]
    c["current_index"] = 0
    c["phase"] = "combat"
    c["initiative"] = [
        {"key": "player", "name": "Kael", "value": 20},
        {"key": "enemy:0", "name": "Goblin", "value": 10},
    ]

    monkeypatch.setattr(combat, "roll_d20", lambda: 19)  # ally-initiativ = 19 + 4 = 23

    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 4}])

    keys = [e["key"] for e in c["turn_order"]]
    assert "ally-0" in keys
    # Sorterade fallande: Mimmrick (23) först, sedan spelaren (20), goblinen (10)
    assert keys[0] == "ally-0"
    assert keys[1] == "player"
    assert keys[2] == "enemy:0"
    # current_index pekar fortfarande på spelarens entry
    assert c["turn_order"][c["current_index"]]["key"] == "player"
    # Frontend-initiativlistan är synkad med turordningen
    assert [i["key"] for i in c["initiative"]] == keys


# ── roll_initiative ─────────────────────────────────────────────────────

def test_roll_initiative_includes_ally_entries():
    state = _make_state()
    _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 2}])

    combat.roll_initiative(state, player_roll=10)

    order = state["world"]["combat"]["turn_order"]
    keys = [e["key"] for e in order]
    assert "player" in keys
    assert "ally-0" in keys
    ally_entry = next(e for e in order if e["key"] == "ally-0")
    assert ally_entry["name"] == "Mimmrick"
    assert ally_entry["acted"] is False
    assert isinstance(ally_entry["initiative"], int)
    # Sorterade fallande
    inits = [e["initiative"] for e in order]
    assert inits == sorted(inits, reverse=True)
    # Frontend-formatet synkat
    assert any(i["key"] == "ally-0" for i in state["world"]["combat"]["initiative"])


# ── ally_turn ───────────────────────────────────────────────────────────

def test_ally_turn_deals_damage_and_logs(monkeypatch):
    state = _make_state()
    _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 4, "damage_dice": "1d6+2"}])
    ally = state["world"]["combat"]["allies"][0]
    enemy = state["world"]["combat"]["enemies"][0]

    monkeypatch.setattr(combat, "roll_d20", lambda: 15)  # 15+4=19 mot AC 12 → träff
    monkeypatch.setattr(combat, "roll_dice", lambda notation: (6, [6]))

    result = combat.ally_turn(state, ally)

    assert result["actions"], "ally_turn ska producera minst en attack"
    hit = result["actions"][0]
    assert hit["hit"] is True
    assert hit["damage"] == 6
    assert enemy["hp"] == 7 - 6  # skadan applicerad på fienden

    ally_log = [e for e in state["world"]["combat"]["log"] if e["actor"] == "ally"]
    assert ally_log, "ally-attack ska loggas med actor 'ally'"
    assert "Goblin" in ally_log[-1]["text"]
    assert "6 skada" in ally_log[-1]["text"]
    assert ally_log[-1]["name"] == "Mimmrick"


def test_ally_turn_miss_logs_ally_entry(monkeypatch):
    state = _make_state()
    _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14, "attack_bonus": 4}])
    ally = state["world"]["combat"]["allies"][0]

    monkeypatch.setattr(combat, "roll_d20", lambda: 1)  # nat 1 → miss

    result = combat.ally_turn(state, ally)

    assert result["actions"][0]["hit"] is False
    ally_log = [e for e in state["world"]["combat"]["log"] if e["actor"] == "ally"]
    assert ally_log and "missar" in ally_log[-1]["text"]


def test_ally_turn_no_enemies_no_crash():
    state = _make_state()
    _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14}])
    ally = state["world"]["combat"]["allies"][0]
    state["world"]["combat"]["enemies"][0]["alive"] = False  # alla fiender döda

    result = combat.ally_turn(state, ally)
    assert result == {"actions": []}


# ── advance_turn ────────────────────────────────────────────────────────

def test_advance_turn_cycles_through_ally_slots():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14}])
    # Deterministisk turordning: spelare → allierad → fiende
    c["turn_order"] = [
        {"key": "player", "name": "Kael", "initiative": 20, "acted": False},
        {"key": "ally-0", "name": "Mimmrick", "initiative": 15, "acted": False},
        {"key": "enemy:0", "name": "Goblin", "initiative": 10, "acted": False},
    ]
    c["current_index"] = 0
    c["phase"] = "combat"

    combat.advance_turn(state)  # spelaren agerade → allierad
    assert c["turn_order"][0]["acted"] is True
    assert c["current_index"] == 1
    assert c["turn_order"][1]["key"] == "ally-0"

    combat.advance_turn(state)  # allieraden agerade → fiende
    assert c["turn_order"][1]["acted"] is True
    assert c["current_index"] == 2

    combat.advance_turn(state)  # fienden agerade → ny runda
    assert c["round"] == 2
    assert c["current_index"] == 0
    assert all(not e["acted"] for e in c["turn_order"])
    assert c["turn_order"][1]["key"] == "ally-0"  # ally-slot finns kvar i rotationen


def test_advance_turn_skips_dead_ally():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14}])
    c["allies"][0]["alive"] = False  # allierad dog
    c["turn_order"] = [
        {"key": "player", "name": "Kael", "initiative": 20, "acted": False},
        {"key": "ally-0", "name": "Mimmrick", "initiative": 15, "acted": False},
        {"key": "enemy:0", "name": "Goblin", "initiative": 10, "acted": False},
    ]
    c["current_index"] = 0

    combat.advance_turn(state)

    # Död allierad hoppas över → fienden är näst på tur
    assert c["current_index"] == 2
    assert c["turn_order"][2]["key"] == "enemy:0"


# ── guardian.apply_mechanics ────────────────────────────────────────────

def test_apply_mechanics_ally_attacks_reduces_enemy_hp_and_logs():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    enemy = c["enemies"][0]
    hp_before = enemy["hp"]

    effects = guardian.apply_mechanics(state, _ally_mech(
        ally_attacks=[
            {"ally": "Mimmrick", "target": "Goblin", "hit": True, "damage": 5,
             "roll": 15, "damage_type": "slashing"},
        ],
    ))

    assert enemy["hp"] == hp_before - 5
    assert enemy["alive"] is True
    ally_log = [e for e in c["log"] if e["actor"] == "ally"]
    assert ally_log, "ally-attack ska loggas med actor 'ally'"
    entry = ally_log[-1]
    assert entry["name"] == "Mimmrick"
    assert "Goblin" in entry["text"] and "5 skada" in entry["text"]
    assert any(e["type"] == "combat_dmg" and e["value"] == "Goblin" for e in effects)


def test_apply_mechanics_ally_attack_miss_logs():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    enemy = c["enemies"][0]
    hp_before = enemy["hp"]

    guardian.apply_mechanics(state, _ally_mech(
        ally_attacks=[
            {"ally": "Mimmrick", "target": "Goblin", "hit": False, "roll": 6},
        ],
    ))

    assert enemy["hp"] == hp_before  # ingen skada på miss
    ally_log = [e for e in c["log"] if e["actor"] == "ally"]
    assert ally_log and "missar" in ally_log[-1]["text"]


def test_apply_mechanics_ally_attacks_ignored_without_enemy_match():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    enemy = c["enemies"][0]
    hp_before = enemy["hp"]

    guardian.apply_mechanics(state, _ally_mech(
        ally_attacks=[
            {"ally": "Mimmrick", "target": "Ormtunga", "hit": True, "damage": 5},
        ],
    ))

    assert enemy["hp"] == hp_before
    assert not any(e["actor"] == "ally" for e in c["log"])


def test_apply_mechanics_ally_death_sets_alive_false():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    ally = c["allies"][0]

    effects = guardian.apply_mechanics(state, _ally_mech(
        ally_damage=[
            {"ally": "Mimmrick", "amount": 99, "attacker": "Goblin", "damage_type": "piercing"},
        ],
    ))

    assert ally["hp"] == 0
    assert ally["alive"] is False
    assert any(e["type"] == "ally_död" and e["value"] == "Mimmrick" for e in effects)
    # Döden ska synas i stridsloggen
    assert any(e["actor"] == "system" and "Mimmrick" in e["text"] and "faller" in e["text"] for e in c["log"])


def test_apply_mechanics_ally_damage_reduces_hp():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 10, "ac": 14}])
    ally = c["allies"][0]

    effects = guardian.apply_mechanics(state, _ally_mech(
        ally_damage=[
            {"ally": "Mimmrick", "amount": 4, "attacker": "Goblin", "damage_type": "piercing"},
        ],
    ))

    assert ally["hp"] == 6
    assert ally["alive"] is True
    assert any(e["type"] == "ally_dmg" and e["amount"] == 4 for e in effects)


# ── [ALLIERAD:]-taggen i main.py ────────────────────────────────────────

def _import_main():
    """Lazy-import av main.py (FastAPI-app — kräver backend/.env på värden)."""
    import main  # noqa: PLC0415
    return main


def test_parse_allierad_tag_adds_allies_to_active_combat():
    main = _import_main()
    state = _make_state()
    _start_combat(state)

    text = "Mimmrick rycker in med svärdet! [ALLIERAD:Mimmrick|12|14, Tord|9|12] Resten av narrationen."
    clean, effects = main._parse_allierad_tag(text, state)

    assert "[ALLIERAD:" not in clean
    assert "Mimmrick rycker in med svärdet!" in clean
    assert "Resten av narrationen." in clean

    allies = state["world"]["combat"]["allies"]
    assert [a["name"] for a in allies] == ["Mimmrick", "Tord"]
    assert allies[0]["hp"] == 12 and allies[0]["ac"] == 14
    assert allies[1]["hp"] == 9 and allies[1]["ac"] == 12
    assert any(e["type"] == "ally_add" for e in effects)
    assert state["meta"]["combat_tag_dirty"] is True


def test_parse_allierad_tag_ignored_without_active_combat():
    main = _import_main()
    state = _make_state()  # ingen strid alls

    text = "[ALLIERAD:Mimmrick|12|14] Ingen strid här."
    clean, effects = main._parse_allierad_tag(text, state)

    # Taggen stripas ur narrationen ändå — men inga allierade skapas
    assert "[ALLIERAD:" not in clean
    assert effects == []
    assert "combat" not in state.get("world", {})


def test_parse_strid_tag_behavior_unchanged():
    """Säkerhetsnät: [STRID:]-flödet måste fungera precis som förut."""
    main = _import_main()
    state = _make_state()

    text = "Gobliner anfaller! [STRID:Goblin|7|12]"
    clean, effects = main._parse_strid_tag(text, state)

    assert "[STRID:" not in clean
    combat_state = state["world"]["combat"]
    assert combat_state["active"] is True
    assert combat_state["enemies"][0]["name"] == "Goblin"
    assert combat_state["enemies"][0]["hp"] == 7
    assert any(e["type"] == "combat_start" for e in effects)


# ── [COMBAT:]-serialisering ─────────────────────────────────────────────

def test_combat_tag_includes_allies():
    state = _make_state()
    c = _start_combat(state)
    combat.add_allies(state, [{"name": "Mimmrick", "hp": 12, "ac": 14}])

    tag = combat.combat_tag(c)
    assert tag.startswith("[COMBAT:")
    assert "allies" in tag
    assert "Mimmrick" in tag
