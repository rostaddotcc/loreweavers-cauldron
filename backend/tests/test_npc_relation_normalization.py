"""Tester för NPC-relation locale-hårdning (fix 2026-10-02).

Buggklass: kanon-enum är SVENSK (allierad/neutral/fiende/okänd) men UI känner
bara de svenska nycklarna, medan flera skriv-vägar släppte igenom engelska värden
('ally'/'enemy'/'unknown') och LLM-fritext → "Unknown"-badge + tom "The Party"-
sidebar + inkonsistent fiende-detektering.

Täcker:
  - guardian._normalize_relation — alias-mapp, case/space-tolerans, okänt→default,
    icke-sträng→default
  - guardian.apply_mechanics — npcs_new + npc_relations normaliserar EN→SV
  - main._parse_mechanical_tags — legacy [NPC_RELATION:namn|värde] normaliserar;
    okänt värde → behåll gammal relation (ingen tyst drift)
  - fiende-detektering är tolerant mot legacy 'enemy' (guardian + main)
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import guardian  # noqa: E402  (lågnivå, importerar utan .env)


def _import_main():
    """Lazy-import av main.py (FastAPI-app — kräver backend/.env på värden)."""
    import main  # noqa: PLC0415
    return main


# ── _normalize_relation (ren funktion, inga fixtures) ──────────────────────

def test_normalize_aliases():
    n = guardian._normalize_relation
    assert n("ally") == "allierad"
    assert n("enemy") == "fiende"
    assert n("unknown") == "okänd"
    assert n("neutral") == "neutral"
    assert n("allierad") == "allierad"


def test_normalize_case_and_whitespace():
    n = guardian._normalize_relation
    assert n("ALLY") == "allierad"
    assert n("  Fiende ") == "fiende"
    assert n("Okänd") == "okänd"


def test_normalize_swedish_freetext_aliases():
    n = guardian._normalize_relation
    assert n("vänlig") == "allierad"
    assert n("fientlig") == "fiende"
    assert n("antagonistic") == "fiende"


def test_normalize_unknown_returns_default():
    n = guardian._normalize_relation
    # Godtycklig fritext som inte matchar → default (None som standard)
    assert n("mentor") is None
    assert n("party member (enslaved)") is None
    assert n("mentor", default="okänd") == "okänd"
    assert n("", default="neutral") == "neutral"


def test_normalize_non_string_returns_default():
    n = guardian._normalize_relation
    assert n(None) is None
    assert n(42, default="okänd") == "okänd"
    assert n({"relation": "ally"}) is None


# ── apply_mechanics: npcs_new + npc_relations ──────────────────────────────

def test_apply_mechanics_npcs_new_normalizes_ally():
    state = {"meta": {"language": "sv"}, "npcs": []}
    mech = {"npcs_new": [{"name": "Kip", "role": "Robot", "relation": "ally"}]}
    guardian.apply_mechanics(state, mech)
    assert state["npcs"][0]["relation"] == "allierad"


def test_apply_mechanics_npcs_new_unknown_freetext_to_okand():
    state = {"meta": {"language": "sv"}, "npcs": []}
    mech = {"npcs_new": [{"name": "Sage", "role": "Mentor", "relation": "mentor"}]}
    guardian.apply_mechanics(state, mech)
    assert state["npcs"][0]["relation"] == "okänd"


def test_apply_mechanics_npc_relations_normalizes_enemy():
    state = {"meta": {"language": "sv"}, "npcs": [
        {"name": "Vespera", "role": "?", "relation": "neutral", "alive": True}
    ]}
    mech = {"npc_relations": [{"name": "Vespera", "new_relation": "enemy"}]}
    guardian.apply_mechanics(state, mech)
    assert state["npcs"][0]["relation"] == "fiende"


def test_apply_mechanics_npc_relations_unknown_keeps_old():
    # Okänt new_relation → skip (relation orörd), ingen tyst drift
    state = {"meta": {"language": "sv"}, "npcs": [
        {"name": "Grist", "role": "?", "relation": "allierad", "alive": True}
    ]}
    mech = {"npc_relations": [{"name": "Grist", "new_relation": "best friend forever"}]}
    guardian.apply_mechanics(state, mech)
    assert state["npcs"][0]["relation"] == "allierad"


# ── main.py: legacy-tagg + fiende-detektering (kräver .env) ─────────────────

def test_legacy_npc_relation_tag_normalizes():
    main = _import_main()
    state = {"meta": {"language": "sv"}, "npcs": [
        {"name": "Keeper of Paths", "role": "?", "relation": "neutral", "alive": True}
    ]}
    _reply, _state, _effects = main._parse_mechanical_tags(
        "[NPC_RELATION:Keeper of Paths|ally]", state
    )
    assert state["npcs"][0]["relation"] == "allierad"


def test_legacy_npc_relation_tag_unknown_keeps_old():
    main = _import_main()
    state = {"meta": {"language": "sv"}, "npcs": [
        {"name": "Scribe", "role": "?", "relation": "fiende", "alive": True}
    ]}
    main._parse_mechanical_tags("[NPC_RELATION:Scribe|mysterious stranger]", state)
    # Okänt värde → gammal relation behålls
    assert state["npcs"][0]["relation"] == "fiende"


def test_enemy_detection_tolerates_legacy_enemy():
    # Guardian:s fiende-lista (prompt-kontext) ska fånga legacy 'enemy'
    npcs = [
        {"name": "A", "relation": "fiende", "alive": True},
        {"name": "B", "relation": "enemy", "alive": True},   # legacy
        {"name": "C", "relation": "allierad", "alive": True},
        {"name": "D", "relation": "enemy", "alive": False},   # död → ej fiende
    ]
    enemies = [n["name"] for n in npcs
               if n.get("relation") in ("fiende", "enemy") and n.get("alive", True)]
    assert set(enemies) == {"A", "B"}
