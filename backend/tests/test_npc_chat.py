"""Tester för @-NPC-chatt: spelaren pratar direkt med en NPC.

Täcker:
  - main._find_at_target — @-detektering (fullt namn, första ordet, ingen match)
  - main._build_npc_chat_context — kontextblock (svenska/engelska, roll/relation/notes)
  - main._maybe_inject_npc_context — injektion i systemprompten
    (levande icke-fiende → injiceras; fiende → inte; död → inte; ingen match → oförändrad)
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _import_main():
    """Lazy-import av main.py (FastAPI-app — kräver backend/.env på värden)."""
    import main  # noqa: PLC0415
    return main


def _npc(**overrides) -> dict:
    """Minimal NPC-dict (samma fält som _parse_npcs producerar)."""
    npc = {
        "name": "Mimmrick Fjäderpung",
        "role": "Kringelfarare",
        "relation": "allierad",
        "notes": "Älskar gåtor och gammal musik.",
        "alive": True,
    }
    npc.update(overrides)
    return npc


def _state(**overrides) -> dict:
    """Minimal spelstate med språk + NPC-lista."""
    state = {
        "meta": {"language": "sv"},
        "npcs": [_npc()],
    }
    state.update(overrides)
    return state


# ── _find_at_target: detektering ────────────────────────────────────────

def test_find_at_target_full_name_match():
    main = _import_main()
    npcs = [_npc()]
    hit = main._find_at_target("@Mimmrick Fjäderpung, jag behöver råd!", npcs)
    assert hit is not None
    assert hit["name"] == "Mimmrick Fjäderpung"


def test_find_at_target_full_name_mid_message():
    """Fullt namn mitt i meddelandet matchar också."""
    main = _import_main()
    npcs = [_npc()]
    hit = main._find_at_target("Säg mig, @Mimmrick Fjäderpung — vad vet du?", npcs)
    assert hit is not None
    assert hit["name"] == "Mimmrick Fjäderpung"


def test_find_at_target_case_insensitive():
    main = _import_main()
    npcs = [_npc()]
    assert main._find_at_target("@mimmrick fjÄderpung: hjälp!", npcs) is not None


def test_find_at_target_first_word_at_start():
    """Bara första ordet av ett flerordigt namn, i början av meddelandet."""
    main = _import_main()
    npcs = [_npc()]
    hit = main._find_at_target("@Mimmrick: hjälp mig!", npcs)
    assert hit is not None
    assert hit["name"] == "Mimmrick Fjäderpung"


def test_find_at_target_first_word_single_name():
    main = _import_main()
    npcs = [{"name": "Tord", "role": "Smed", "relation": "neutral", "alive": True}]
    hit = main._find_at_target("@Tord vad vet du?", npcs)
    assert hit is not None
    assert hit["name"] == "Tord"


def test_find_at_target_no_partial_word_match():
    """'@Tordsson' får INTE matcha NPC:n 'Tord' — namn måste sluta vid ordgräns."""
    main = _import_main()
    npcs = [{"name": "Tord", "role": "Smed", "relation": "neutral", "alive": True}]
    assert main._find_at_target("@Tordsson hälsar", npcs) is None


def test_find_at_target_no_match():
    main = _import_main()
    npcs = [_npc()]
    assert main._find_at_target("Jag går till torget.", npcs) is None
    assert main._find_at_target("@Gandalf var är du?", npcs) is None
    assert main._find_at_target("", npcs) is None
    assert main._find_at_target("@", npcs) is None


def test_find_at_target_empty_npcs():
    main = _import_main()
    assert main._find_at_target("@Mimmrick Fjäderpung hej!", []) is None


# ── _build_npc_chat_context: kontextblock ───────────────────────────────

def test_build_context_swedish():
    main = _import_main()
    block = main._build_npc_chat_context(_npc(), "sv")
    assert "Mimmrick Fjäderpung" in block
    assert "I KARAKTÄR" in block
    assert "Kringelfarare" in block            # roll
    assert "allierad" in block                 # relation
    assert "Älskar gåtor" in block             # notes
    assert "NPC-SAMTAL" in block


def test_build_context_english():
    main = _import_main()
    block = main._build_npc_chat_context(_npc(), "en")
    assert "Mimmrick Fjäderpung" in block
    assert "IN CHARACTER" in block
    assert "Kringelfarare" in block            # roll
    assert "allierad" in block                 # relation
    assert "Älskar gåtor" in block             # notes
    assert "NPC CONVERSATION" in block


def test_build_context_omits_missing_notes():
    main = _import_main()
    npc = _npc(notes="", role="")
    sv = main._build_npc_chat_context(npc, "sv")
    en = main._build_npc_chat_context(npc, "en")
    assert "Anteckningar" not in sv
    assert "Roll" not in sv
    assert "Notes" not in en
    assert "Role" not in en
    # Relationen finns alltid med
    assert "allierad" in sv and "allierad" in en


# ── _maybe_inject_npc_context: injektion i systemprompten ───────────────

def test_inject_alive_non_enemy():
    main = _import_main()
    state = _state()
    out = main._maybe_inject_npc_context("SYSTEMPROMPT", "@Mimmrick Fjäderpung: berätta om gåtan!", state)
    assert out != "SYSTEMPROMPT"
    assert out.startswith("SYSTEMPROMPT")      # appenrad, inte ersatt
    assert "\n\n## 💬 NPC-SAMTAL" in out
    assert "Mimmrick Fjäderpung" in out
    assert "I KARAKTÄR" in out


def test_inject_neutral_npc():
    """Neutral (men levande) NPC injiceras också."""
    main = _import_main()
    state = _state(npcs=[_npc(relation="neutral")])
    out = main._maybe_inject_npc_context("SYS", "@Mimmrick: hej!", state)
    assert "NPC-SAMTAL" in out


def test_inject_skipped_for_enemy():
    main = _import_main()
    state = _state(npcs=[_npc(relation="fiende")])
    out = main._maybe_inject_npc_context("SYS", "@Mimmrick: du ska dö!", state)
    assert out == "SYS"


def test_inject_skipped_for_dead():
    main = _import_main()
    state = _state(npcs=[_npc(alive=False)])
    out = main._maybe_inject_npc_context("SYS", "@Mimmrick: vakna!", state)
    assert out == "SYS"


def test_inject_skipped_no_match():
    """Ingen @-match → systemprompten oförändrad (bakåtkompatibilitet)."""
    main = _import_main()
    state = _state()
    out = main._maybe_inject_npc_context("SYS", "Jag går till torget.", state)
    assert out == "SYS"


def test_inject_english_campaign():
    main = _import_main()
    state = _state()
    state["meta"]["language"] = "en"
    out = main._maybe_inject_npc_context("SYS", "@Mimmrick Fjäderpung hello!", state)
    assert "## 💬 NPC CONVERSATION" in out
    assert "IN CHARACTER" in out


def test_inject_skipped_when_no_npcs_in_state():
    main = _import_main()
    state = _state(npcs=[])
    out = main._maybe_inject_npc_context("SYS", "@Mimmrick hej!", state)
    assert out == "SYS"
