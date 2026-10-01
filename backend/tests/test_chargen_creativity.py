"""Tester för char-gen-promptens kreativitetsspår + kodnät (2026-10-01).

Täckning:
  1. Prompten: gamla självmodsägande namnregler borta, "spelarens önskemål
     är heligt" + kreativitetsspårs-hänvisning närvarande (SV + EN).
  2. _build_chargen_seed_block: slumpad mångfald, båda språken, undvik-
     namn rad endast när spelaren har tidigare karaktärer.
  3. _recent_character_names: hämtar ur valv + kampanjer, deduppar.
  4. Kodnätet i _finalize_character_data: saves (SV-klassnamn!), hp,
     spell_slots, speed — och att modellens rimliga värden INTE rörs.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import state_manager as sm  # noqa: E402


@pytest.fixture(autouse=True)
def _no_disk_save(monkeypatch, tmp_path):
    """Inga skrivningar till riktiga kampanj-/valvkataloger."""
    monkeypatch.setattr(main.store, "save", lambda state: None)
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(sm, "VAULTS_DIR", tmp_path / "vaults")


# ── 1. Promptinnehåll ──────────────────────────────────────────────────

def test_old_self_contradicting_name_rules_removed():
    for p in (main.CHARACTER_PROMPT_SV, main.CHARACTER_PROMPT_EN):
        assert "FÖRBJUDNA NAMN" not in p
        assert "FORBIDDEN NAMES" not in p
        # den omöjliga statlösa regeln får inte finnas kvar
        assert "tidigare svar" not in p
        assert "previous answers" not in p
        # "aldrig samma som promptens exempel" är borttagen
        assert "som i promptens exempel" not in p
        assert "as any example in the prompt" not in p


def test_player_wish_sacred_present_in_both_langs():
    assert "SPELARENS ÖNSKEMÅL ÄR HELIGT" in main.CHARACTER_PROMPT_SV
    assert "THE PLAYER'S WISH IS SACRED" in main.CHARACTER_PROMPT_EN


def test_hardcoded_schema_values_replaced_by_compute_directives():
    for p in (main.CHARACTER_PROMPT_SV, main.CHARACTER_PROMPT_EN):
        assert '"current": 10, "max": 10' not in p
        assert '"spell_slots": {"current": 0, "max": 0}' not in p
        assert '"speed": "30 ft"' not in p


# ── 2. Seed-block ──────────────────────────────────────────────────────

def test_seed_block_diversity():
    blocks = {main._build_chargen_seed_block("nobody", "en") for _ in range(200)}
    # 13 kulturer × 6 namnformer × 8 twists = 624 spår — 200 dragningar
    # bör landa på minst 150 unika.
    assert len(blocks) >= 150


def test_seed_block_lang_structure():
    sv = main._build_chargen_seed_block("nobody", "sv")
    en = main._build_chargen_seed_block("nobody", "en")
    assert "KREATIVITETSSPÅR" in sv and "Namnkultur" in sv and "Koncept-twist" in sv
    assert "CREATIVITY TRACK" in en and "Naming culture" in en and "Concept twist" in en
    # utan sparade karaktärer: ingen undvik-rad
    assert "Undvik nyligen använda namn" not in sv
    assert "Avoid recently used names" not in en


def test_seed_block_includes_recent_names(monkeypatch):
    sm.CharacterVault().save("alice", {"name": "Sigge Stenbrott"}, "Kampanj 1")
    sm.CharacterVault().save("alice", {"name": "Yrsa Eldhand"}, "Kampanj 2")
    block = main._build_chargen_seed_block("alice", "sv")
    assert "Sigge Stenbrott" in block and "Yrsa Eldhand" in block
    assert "Undvik nyligen använda namn" in block


# ── 3. Namn-dedup ──────────────────────────────────────────────────────

def test_recent_character_names_dedups_and_orders(monkeypatch):
    v = sm.CharacterVault()
    v.save("bob", {"name": "Först"}, "c1")
    v.save("bob", {"name": "Sist"}, "c2")
    v.save("bob", {"name": "Sist"}, "c3")  # dubblett → en gång
    names = main._recent_character_names("bob")
    assert names[0] == "Sist"  # senast sparad först
    assert set(names) == {"Först", "Sist"}


def test_recent_character_names_empty_for_unknown_user():
    assert main._recent_character_names("ingen-sån") == []


# ── 4. Kodnät i _finalize_character_data ───────────────────────────────

def test_saves_fallback_handles_swedish_class_names():
    char_data = {"name": "T", "class": "Munk", "race": "humani"}
    out, _, _ = main._finalize_character_data(char_data, "sv")
    assert [s["name"] for s in out["saves"]] == ["STR", "DEX"]  # 5e-correct (inte DEX+INT)


def test_saves_fallback_ranger():
    char_data = {"name": "T", "class": "Jägare", "race": "human"}
    out, _, _ = main._finalize_character_data(char_data, "sv")
    assert [s["name"] for s in out["saves"]] == ["STR", "DEX"]


def test_saves_model_value_not_overridden():
    char_data = {"name": "T", "class": "wizard", "saves": [{"name": "CON", "prof": True}]}
    out, _, _ = main._finalize_character_data(char_data, "en")
    assert out["saves"] == [{"name": "CON", "prof": True}]


def test_hp_backstop_from_hit_die_and_con():
    # Barbar (d12) med CON 14 (+2) utan hp → 14 HP
    char_data = {
        "name": "T", "class": "Barbarian",
        "abilities": {"CON": {"score": 14, "mod": 2}},
    }
    out, _, _ = main._finalize_character_data(char_data, "sv")
    assert out["hp"]["max"] == 14 and out["hp"]["current"] == 14


def test_hp_model_value_kept():
    char_data = {"name": "T", "class": "fighter",
                 "hp": {"current": 11, "max": 11, "temp": 0}}
    out, _, _ = main._finalize_character_data(char_data, "en")
    assert out["hp"] == {"current": 11, "max": 11, "temp": 0}


def test_spell_slots_backstop_wizard_gets_two():
    char_data = {"name": "T", "class": "Trollkarl", "spells": [{"name": "Eldklot", "level": 0}]}
    out, _, _ = main._finalize_character_data(char_data, "sv")
    assert out["spell_slots"] == {"current": 2, "max": 2}


def test_spell_slots_backstop_warlock_gets_one():
    char_data = {"name": "T", "class": "warlock"}
    out, _, _ = main._finalize_character_data(char_data, "en")
    assert out["spell_slots"]["max"] == 1


def test_spell_slots_noncaster_stays_zero():
    char_data = {"name": "T", "class": "Rogue", "spell_slots": {"current": 0, "max": 0}}
    out, _, _ = main._finalize_character_data(char_data, "en")
    assert out["spell_slots"]["max"] == 0


def test_spell_slots_model_value_kept():
    char_data = {"name": "T", "class": "cleric", "spell_slots": {"current": 3, "max": 3}}
    out, _, _ = main._finalize_character_data(char_data, "en")
    assert out["spell_slots"] == {"current": 3, "max": 3}


def test_speed_backstop_dwarf_halfling():
    char_data = {"name": "T", "class": "fighter", "race": "Dvärg"}
    out, _, _ = main._finalize_character_data(char_data, "sv")
    assert out["speed"] == "25 ft"
    char_data2 = {"name": "T", "class": "rogue", "race": "human"}
    out2, _, _ = main._finalize_character_data(char_data2, "en")
    assert out2["speed"] == "30 ft"
