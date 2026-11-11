"""Regression: stridsmotorns rund-/snapshot-buggar (playtest 2026-09-13,
kampanj mainchat/051130a1a73d — 14 turer, runda 1).

Symtom (verifierade i state.json + session-001.jsonl):
  1) Rundan fastnade på 1 hela striden — DM sänder aldrig combat_round-siffror
     och _advance_turn var död kod (tom turn_order). Fasen stod kvar på
     'awaiting_initiative' även mitt i pågående strid.
  2) 'After the turn:'-snapshots: 6+ IDENTISKA rader per runda (varje handler
     appade sin mitten-i-strömmen) OCH undanlagda HP ('Rust-Husk 22/22' efter
     -6 och -6 redan tillämpade).
  3) combat_end lämnade fiender med hp>0 alive=true fast loggen sa 'defeated'.
  4) _tick_all_statuses avlossades aldrig (berodde på den döda cr-signalen).

Fix: server-driven round_acted-bokföring i apply_mechanics (guardian.py
_auto_advance_round), en enda slutlig snapshot per anrop
(_append_turn_snapshot), strids-slut-städ i combat_end-handläggaren.

Täcker:
  (a) runda avanceras EXAKT EN gång när spelare + alla levande fiender agerat
  (b) ingen avancemang vid halva rundan (bara spelaren / bara fienden)
  (c) en snapshot per anrop, med korrekt (slutlig) HP
  (d) inga dubblett-snapshots över anrop (samma text → replace-in-place)
  (e) combat_end nollnar defeated-fiende (mech['defeated'] + 'falls!'-spår)
  (f) statusar tickas vid auto-avancerad runda
  (g) LLM combat_round högre nummer förblir auktoritativt
  (h) fas 'active' vid guardian combat_start + vid första attacken
  (i) tolererar äldre combat-dict UTAN round_acted/turn_order
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import combat  # noqa: E402
import guardian  # noqa: E402


def _make_state(hp: int = 9) -> dict:
    """Minimal spelstate — Qyrel Voss, AC 12 (playtest-karaktären)."""
    return {
        "meta": {"turn_count": 7},
        "character": {
            "name": "Qyrel Voss",
            "hp": {"current": hp, "max": 9, "temp": 0},
            "ac": 12,
        },
        "inventory": [],
        "npcs": [],
        "world": {},
    }


def _start_combat(state: dict, enemies: list[dict] | None = None) -> dict:
    return combat.start_combat(state, enemies or [
        {"name": "Rust-Husk", "hp": 22, "ac": 13, "attack_bonus": 3, "damage_dice": "1d6+1"},
    ])


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
    """Styr kodens fiendetagningar: d20 i följd, sedan skaderullar."""
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


def _snapshots(c: dict) -> list[dict]:
    return [e for e in c.get("log", []) if isinstance(e, dict) and e.get("snapshot")]


# ── (a)+(b) server-driven rund-avancering ──────────────────────────────

def test_round_advances_exactly_once_when_player_and_enemies_acted(monkeypatch):
    """Spelaren attackerar + fienden attackerar SAMMA anrop → runda 1→2,
    EXAKT en gång (ingen kedje-avancering)."""
    state = _make_state()
    c = _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])  # 17+3=20 ≥ AC 12 → träff

    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 6}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])

    assert c["round"] == 2
    banners = [e for e in c["log"] if "── ROUND 2 ──" in e.get("text", "")]
    assert len(banners) == 1
    assert banners[0]["round"] == 2
    # rund-bokföringen tömd → nästa runda börjar om från noll
    assert c["round_acted"] == {"player": False, "enemies": {}}
    # spelaren får fulla handlingar igen
    assert c["player_actions"] == {"action": True, "bonus": True, "reaction": True}


def test_round_holds_when_only_player_acted(monkeypatch):
    state = _make_state()
    c = _start_combat(state)
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 6}],
    ), skip_effects=[])
    assert c["round"] == 1
    assert c["round_acted"]["player"] is True
    assert c["round_acted"]["enemies"]["Rust-Husk#0"] is False  # index-nyckel: dubletter får Egna flaggor


def test_round_holds_when_only_enemies_acted(monkeypatch):
    state = _make_state()
    c = _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[4], dmg_seq=[])  # miss
    guardian.apply_mechanics(state, _mech(
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])
    assert c["round"] == 1
    assert c["round_acted"]["player"] is False
    assert c["round_acted"]["enemies"]["Rust-Husk#0"] is True


def test_two_enemies_both_must_act(monkeypatch):
    """Med två fiender: bara den ene attackerad → ingen rund-avancering;
    andra turen attackerar den andre → rundan går vidare."""
    state = _make_state()
    c = _start_combat(state, [
        {"name": "Husk A", "hp": 10, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"},
        {"name": "Husk B", "hp": 10, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"},
    ])
    _mock_dice(monkeypatch, d20_seq=[17, 17], dmg_seq=[(2, [2]), (2, [2])])
    # tur 1: spelaren + Husk A
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Husk A", "hit": True, "damage": 1}],
        enemy_attacks=[{"attacker": "Husk A"}],
    ), skip_effects=[])
    assert c["round"] == 1
    # tur 2: Husk B attackerar → grinden uppfylld
    guardian.apply_mechanics(state, _mech(
        enemy_attacks=[{"attacker": "Husk B"}],
    ), skip_effects=[])
    assert c["round"] == 2


def test_dead_enemy_not_blocking_round(monkeypatch):
    """En död fiende ska aldrig spärra rundavancering — grinden gäller bara
    LEVANDE fiender."""
    state = _make_state()
    c = _start_combat(state, [
        {"name": "Slain", "hp": 4, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"},
        {"name": "Alive", "hp": 20, "ac": 10, "attack_bonus": 3, "damage_dice": "1d6"},
    ])
    c["enemies"][0]["alive"] = False  # död sedan tidigare
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(2, [2])])
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Alive", "hit": True, "damage": 3}],
        enemy_attacks=[{"attacker": "Alive"}],
    ), skip_effects=[])
    assert c["round"] == 2


# ── (c)+(d) snapshots ───────────────────────────────────────────────────

def test_single_snapshot_with_correct_hp(monkeypatch):
    """Player-attack (-6) OCH enemy-attack samma anrop → EXAKT en snapshot
    för anropet, med SLUTLIG hp (16/22 — aldrig det undanlagda 22/22)."""
    state = _make_state()
    c = _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])

    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 6}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])

    snaps_r1 = [s for s in _snapshots(c) if s["round"] == 1]
    assert len(snaps_r1) == 1
    txt = snaps_r1[0]["text"]
    assert "Rust-Husk 16/22 HP" in txt
    assert "22/22" not in txt          # aldrig stake HP efter tillämpad skada
    assert "Qyrel Voss 6/9 HP" in txt  # spelaren först, post-enemy-damage


def test_no_duplicate_identical_snapshots_across_calls(monkeypatch):
    """Två på varandra följande anrop med oförändrat HP (allt miss) →
    identisk snapshot-text får ALDRIG dupliceras (replace-in-place)."""
    state = _make_state()
    c = _start_combat(state)
    _mock_dice(monkeypatch, d20_seq=[4], dmg_seq=[])
    mech = _mech(enemy_attacks=[{"attacker": "Rust-Husk"}])
    guardian.apply_mechanics(state, mech, skip_effects=[])
    first_snap = c["log"][-1]["text"]
    # andra anropet: ingen HP-förändring alls → samma snapshot-text
    guardian.apply_mechanics(state, _mech(combat_events=["narrativt plum"]), skip_effects=[])
    snaps = [s for s in _snapshots(c) if s["round"] == 1]
    texts = [s["text"] for s in snaps]
    assert texts.count(first_snap) == 1, f"identiska snapshots köade: {texts}"


# ── (e) combat_end nollnar narrativt döda ──────────────────────────────

def test_combat_end_zeroes_defeated_enemy_via_defeated_list():
    """Playtest-scenariot: Rust-Husk 'defeated' vid 10/22 — mech['defeated']
    nollar fienden (hp=0, alive=false)."""
    state = _make_state()
    c = _start_combat(state)
    c["enemies"][0]["hp"] = 10
    c["log"].append({"round": 1, "actor": "player", "name": "Qyrel Voss", "text": "misses Rust-Husk"})
    guardian.apply_mechanics(state, _mech(
        combat_end={"reason": "Rust-Husk defeated"}, defeated=["Rust-Husk"],
    ), skip_effects=[])
    e = c["enemies"][0]
    assert e["hp"] == 0 and e["alive"] is False
    assert c["active"] is False
    assert not any("still standing" in x.get("text", "") for x in c["log"])


def test_combat_end_zeroes_enemy_via_falls_log():
    """Utan defeated-lista: fiende vars senaste EGEN loggrad är 'falls!'
    nollas ändå (loggade 'falls!' men HP stannade på 10 pga annat flöde)."""
    state = _make_state()
    c = _start_combat(state)
    c["enemies"][0]["hp"] = 10
    c["log"].append({"round": 1, "actor": "system", "name": "", "text": "Rust-Husk falls!"})
    guardian.apply_mechanics(state, _mech(
        combat_end={"reason": "monster destroyed", "defeated": ["Rust-Husk"]},
    ), skip_effects=[])
    e = c["enemies"][0]
    assert e["hp"] == 0 and e["alive"] is False


def test_combat_end_keeps_standing_enemy_and_logs():
    """Levande fiende utan döds-spår lämnas orörd — men loggen säger att
    hen står kvar."""
    state = _make_state()
    c = _start_combat(state)
    c["enemies"][0]["hp"] = 14
    guardian.apply_mechanics(state, _mech(
        combat_end={"reason": "spelaren flyr"},
    ), skip_effects=[])
    e = c["enemies"][0]
    assert e["hp"] == 14 and e["alive"] is True
    assert any("combat ended — 1 enemies still standing" in x.get("text", "") for x in c["log"])


# ── (f) status-tick på auto-avancerad runda ────────────────────────────

def test_statuses_tick_on_auto_advanced_round(monkeypatch):
    """Poison på fienden (2 skada/runda): när rundan auto-avanceras TILLAS
    status-skadan — tidigare dog den vägen tillsammans med den döda
    combat_round-signalen."""
    state = _make_state()
    c = _start_combat(state)
    combat.add_status(c["enemies"][0], "poison", duration=3)
    c["enemies"][0]["hp"] = 20  # utrymme för poison-skada
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])

    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": False}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])

    assert c["round"] == 2
    assert c["enemies"][0]["hp"] == 20 - 2  # poison tickad vid rundstart
    assert any("poison damage" in x.get("text", "") for x in c["log"])


def test_player_statuses_tick_on_auto_advanced_round(monkeypatch):
    state = _make_state(hp=14)
    state["character"]["hp"]["max"] = 14
    c = _start_combat(state)
    state["character"]["statuses"] = [{"name": "burn", "duration": 2, "dmg_per_turn": 3}]
    _mock_dice(monkeypatch, d20_seq=[4], dmg_seq=[])  # fienden missar
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": False}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])
    assert c["round"] == 2
    assert state["character"]["hp"]["current"] == 11  # 14 - 3 brännskada


# ── (g) LLM combat_round förblir auktoritativt ─────────────────────────

def test_llm_combat_round_higher_number_authoritative_and_syncs_bookkeeping(monkeypatch):
    """mech['combat_round']=4 (högre) → rundan sätts till 4 AV koden,
    round_acted töms — auto-avanceringen lägger inte på ovanpå."""
    state = _make_state()
    c = _start_combat(state)
    c["round_acted"] = {"player": True, "enemies": {"Rust-Husk": True}}
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])
    guardian.apply_mechanics(state, _mech(
        combat_round=4,
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 2}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])
    assert c["round"] == 4  # INTE 5 — ingen dubbelräkning
    assert c["round_acted"] == {"player": False, "enemies": {}}


def test_llm_combat_round_equal_number_no_advance():
    state = _make_state()
    c = _start_combat(state)
    guardian.apply_mechanics(state, _mech(combat_round=1), skip_effects=[])
    assert c["round"] == 1


# ── (h) ärlig fas ───────────────────────────────────────────────────────

def test_guardian_combat_start_sets_phase_active():
    state = _make_state()
    guardian.apply_mechanics(state, _mech(
        combat_start={"enemies": [{"name": "Goblin", "hp": 7, "ac": 12, "max_hp": 7}]},
    ), skip_effects=[])
    c = state["world"]["combat"]
    assert c["active"] is True
    assert c["phase"] == "active"


def test_strid_opened_combat_phase_becomes_active_on_first_attack(monkeypatch):
    """[STRID:]-vägen (combat.start_combat) sätter 'awaiting_initiative' —
    så fort någon attackeras ska fasen bli 'active' (playtest: fasen frös)."""
    state = _make_state()
    c = _start_combat(state)
    assert c["phase"] == "awaiting_initiative"
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 6}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])
    assert c["phase"] == "active"


# ── (i) bakåtkompat: äldre combat utan round_acted/turn_order ──────────

def test_combat_without_round_acted_or_turn_order_survives(monkeypatch):
    """Gammal kampanj-state (051130a1a73d innan fixen) — ingen round_acted,
    tom turn_order — ska fungera och avancera rundan korrekt."""
    state = _make_state()
    state["world"]["combat"] = {
        "active": True, "round": 1, "phase": "awaiting_initiative",
        "turn_order": [], "current_index": 0,
        "enemies": [{"id": 0, "name": "Rust-Husk", "hp": 22, "max_hp": 22,
                     "ac": 13, "alive": True, "statuses": [],
                     "attack_bonus": 3, "damage_dice": "1d6+1"}],
        "allies": [], "player_actions": {"action": True, "bonus": True, "reaction": True},
        "log": [], "started_turn": 7, "ended_turn": None, "player_cover": None,
    }
    c = state["world"]["combat"]
    assert "round_acted" not in c  # utgångsläget saknar nyckeln
    _mock_dice(monkeypatch, d20_seq=[17], dmg_seq=[(3, [3])])
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Rust-Husk", "hit": True, "damage": 6}],
        enemy_attacks=[{"attacker": "Rust-Husk"}],
    ), skip_effects=[])
    assert c["round"] == 2
    assert c["enemies"][0]["hp"] == 16
    snaps_r1 = [s for s in _snapshots(c) if s["round"] == 1]
    assert len(snaps_r1) == 1 and "16/22" in snaps_r1[0]["text"]


def test_same_name_enemies_do_not_share_acted_flag(monkeypatch):
    """Regression (live-fynd 2026-09-13): tre 'Archival Sentinel' med samma namn.
    En attack får INTE rundan att avancera; rotationen markerar nästa oanvända
    dublett; när alla tre attackerat + spelaren → runda 2."""
    state = _make_state()
    c = _start_combat(state, [
        {"name": "Sentinel", "hp": 18, "ac": 14, "attack_bonus": 3, "damage_dice": "1d6"},
        {"name": "Sentinel", "hp": 18, "ac": 14, "attack_bonus": 3, "damage_dice": "1d6"},
        {"name": "Sentinel", "hp": 18, "ac": 14, "attack_bonus": 3, "damage_dice": "1d6"},
    ])
    _mock_dice(monkeypatch, d20_seq=[17, 17, 17, 17, 17], dmg_seq=[(2, [2])] * 5)
    # tur 1: spelaren + EN av tre → ingen avancemang, rotation markerar fiende 0
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Sentinel", "hit": True, "damage": 4}],
        enemy_attacks=[{"attacker": "Sentinel"}],
    ), skip_effects=[])
    assert c["round"] == 1
    assert sorted(c["round_acted"]["enemies"].values()) == [False, False, True]
    # tur 2: spelaren + de två sista (två attacker-entries → rotation) → runda 2
    guardian.apply_mechanics(state, _mech(
        player_attacks=[{"target": "Sentinel", "hit": True, "damage": 4}],
        enemy_attacks=[{"attacker": "Sentinel"}, {"attacker": "Sentinel"}],
    ), skip_effects=[])
    assert c["round"] == 2
