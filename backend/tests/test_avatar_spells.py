"""Tester för DM-avatar-promptvariation (v28) + spells (char-gen + Guardian spells_add)."""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import guardian  # noqa: E402


@pytest.fixture(autouse=True)
def _no_disk_save(monkeypatch):
    """Förhindra att _finalize_character skriver riktiga kampanjfiler på disk."""
    monkeypatch.setattr(main.store, "save", lambda state: None)


# ── DM-avatar-prompt ──

def test_dm_avatar_prompt_is_deterministic_per_seed():
    p1 = main._build_dm_avatar_prompt(42)
    p2 = main._build_dm_avatar_prompt(42)
    assert p1 == p2
    assert "Dungeon Master" in p1


def test_dm_avatar_prompt_varies_across_seeds():
    prompts = {main._build_dm_avatar_prompt(s) for s in range(1, 30)}
    # Många seedar → många unika prompts (arketyp × mood × palett)
    assert len(prompts) >= 10


def test_dm_avatar_prompt_has_no_skull_or_horns():
    for seed in range(1, 60):
        p = main._build_dm_avatar_prompt(seed)
        assert "horned mask" not in p
        assert "skull" not in p.lower()
        assert "döskalle" not in p.lower()


def test_dm_avatar_prompt_has_style_and_runes():
    p = main._build_dm_avatar_prompt(7)
    assert main.STEP_IMAGE_STYLE.split(".")[0].strip() in p
    assert "arcane runes" in p


def test_build_avatar_prompt_dm_uses_seeded_variation():
    state = {"character": {}, "npcs": [], "lore": []}
    a = main._build_avatar_prompt(state, "dm", seed=1)
    b = main._build_avatar_prompt(state, "dm", seed=99)
    c = main._build_avatar_prompt(state, "dm", seed=1)
    assert a == c          # deterministiskt per seed
    assert a != b          # olika seed → olika motiv


# ── Char-gen spells-normalisering ──

def _full_state():
    """State som _finalize_character kan spara (kräver meta.user)."""
    return {
        "meta": {
            "campaign_id": "test-camp", "campaign_name": "Test",
            "user": "testuser", "turn_count": 0, "session_count": 1,
        },
        "character": {}, "inventory": [], "npcs": [], "world": {},
        "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0}, "quests": [],
    }


def test_finalize_character_ensures_spells_list():
    char_data = {"name": "Test", "class": "wizard", "race": "human"}
    state = _full_state()
    main._finalize_character(char_data, state, "sv")
    assert char_data["spells"] == []


def test_finalize_character_normalizes_spells():
    char_data = {
        "name": "Test", "class": "wizard", "race": "human",
        "spells": [
            {"name": "Eldklot", "level": 3, "school": "evocation",
             "casting_time": "1 action", "damage_dice": "8d6", "description": "Klot av eld."},
            {"name": "", "level": 0, "school": "", "description": ""},  # skräp — ska filtreras
            "inte ett dict",  # skräp — ska filtreras
        ],
    }
    state = _full_state()
    main._finalize_character(char_data, state, "sv")
    assert len(char_data["spells"]) == 1
    sp = char_data["spells"][0]
    assert sp["name"] == "Eldklot"
    assert sp["level"] == 3
    assert sp["school"] == "evocation"
    assert sp["damage_dice"] == "8d6"


def test_finalize_character_accepts_single_spell_dict():
    char_data = {
        "name": "Test", "class": "sorcerer", "race": "human",
        "spells": {"name": "Magisk missil", "level": 1},
    }
    state = _full_state()
    main._finalize_character(char_data, state, "sv")
    assert len(char_data["spells"]) == 1
    assert char_data["spells"][0]["name"] == "Magisk missil"


# ── Guardian spells_add ──

def _state_with_character():
    return {
        "character": {"name": "Test", "hp": {"current": 10, "max": 10}},
        "inventory": [], "npcs": [], "world": {},
        "meta": {}, "currency": {}, "quests": [],
    }


def test_apply_mechanics_spells_add_appends():
    state = _state_with_character()
    effects = guardian.apply_mechanics(state, {
        "spells_add": [
            {"name": "Eldklot", "level": 0, "school": "evocation",
             "casting_time": "1 action", "damage_dice": "1d10", "description": "Eldklot."},
            {"name": "Sköld", "level": 1, "school": "abjuration",
             "casting_time": "1 reaction", "description": "+5 AC."},
        ],
    })
    spells = state["character"]["spells"]
    assert len(spells) == 2
    assert spells[0]["name"] == "Eldklot"
    assert spells[0]["level"] == 0
    assert spells[1]["name"] == "Sköld"
    assert spells[1]["level"] == 1
    types = [e.get("type") for e in effects]
    assert types.count("spell_add") == 2


def test_apply_mechanics_spells_add_dedup():
    state = _state_with_character()
    state["character"]["spells"] = [{"name": "Eldklot", "level": 0}]
    effects = guardian.apply_mechanics(state, {
        "spells_add": [
            {"name": "Eldklot", "level": 0},
            {"name": "eldklot", "level": 0},  # case-insensitiv dedup
            {"name": "Ny besvärjelse", "level": 1},
        ],
    })
    spells = state["character"]["spells"]
    assert len(spells) == 2  # Eldklot bara en gång
    names = [s["name"] for s in spells]
    assert "Ny besvärjelse" in names


def test_apply_mechanics_spells_add_ignores_garbage():
    state = _state_with_character()
    effects = guardian.apply_mechanics(state, {
        "spells_add": ["inte dict", {"name": ""}, {"level": 3}, None],
    })
    assert state["character"].get("spells", []) == []
    assert not any(e.get("type") == "spell_add" for e in effects)


def test_apply_mechanics_spells_add_creates_key_when_missing():
    state = {"character": {"name": "Utan spells"}, "inventory": [], "npcs": [], "world": {}}
    guardian.apply_mechanics(state, {"spells_add": [{"name": "Välsignelse", "level": 1}]})
    assert state["character"]["spells"][0]["name"] == "Välsignelse"


# ── Guardian npcs_near (närvaro) ──

def _state_with_npcs():
    return {
        "character": {"name": "Test", "hp": {"current": 10, "max": 10}},
        "inventory": [], "world": {},
        "meta": {}, "currency": {}, "quests": [],
        "npcs": [
            {"name": "Alva", "role": "Smed", "relation": "allierad", "near": False},
            {"name": "Tor", "role": "Vakt", "relation": "neutral", "near": False},
            {"name": "Gorm", "role": "Kapten", "relation": "fiende", "near": False},
        ],
    }


def test_apply_mechanics_npcs_near_marks_presence():
    state = _state_with_npcs()
    effects = guardian.apply_mechanics(state, {"npcs_near": ["alva", "tor"]})
    by_name = {n["name"]: n["near"] for n in state["npcs"]}
    assert by_name == {"Alva": True, "Tor": True, "Gorm": False}
    types = [e.get("type") for e in effects]
    assert types.count("npc_near") == 2


def test_apply_mechanics_npcs_near_clears_when_leaves():
    state = _state_with_npcs()
    state["npcs"][0]["near"] = True  # Alva var nära förra turen
    effects = guardian.apply_mechanics(state, {"npcs_near": []})
    by_name = {n["name"]: n["near"] for n in state["npcs"]}
    assert by_name == {"Alva": False, "Tor": False, "Gorm": False}
    # Bara Alva (som lämnade) rapporteras
    near_effects = [e for e in effects if e.get("type") == "npc_near"]
    assert len(near_effects) == 1
    assert "lämnade" in near_effects[0]["value"]


def test_apply_mechanics_npcs_near_ignores_unknown_names():
    state = _state_with_npcs()
    effects = guardian.apply_mechanics(state, {"npcs_near": ["Finns inte", 42, None]})
    assert not any(n["near"] for n in state["npcs"])
    assert not any(e.get("type") == "npc_near" for e in effects)


# ── AI-avatar-prompter: realistiska, öppna, lore-aligned ──

def test_avatar_style_is_realistic_and_open():
    style = main.STEP_IMAGE_STYLE.lower()
    assert "photorealistic" in style or "realistic" in style
    assert "anime" not in style and "cartoon" not in style and "manga" not in style
    # Får inte tvinga humanoid komposition
    assert "head-and-shoulders" not in style


def test_build_avatar_prompt_npc_uses_role_and_notes():
    state = {
        "character": {}, "lore": [], "npcs": [
            {"name": "Drone-7", "role": "patrol drone",
             "notes": "a sleek chrome surveillance drone with a single red eye, hums softly"}
        ],
    }
    p = main._build_avatar_prompt(state, "npc:drone-7")
    assert "patrol drone" in p
    assert "sleek chrome" in p  # notes får inte slängas bara för att role finns


def test_build_avatar_prompt_npc_fallback_is_neutral():
    state = {"character": {}, "lore": [], "npcs": []}
    p = main._build_avatar_prompt(state, "npc:okänd")
    assert "mysterious figure" in p
    assert "dark fantasy" not in p  # inte hårdkodat till fantasy-genre


def test_dm_avatar_prompt_aligns_with_lore():
    state = {"character": {}, "npcs": [], "lore": ["A signal pulses from the obsidian talisman near Veyl's Lantern Court."]}
    p = main._build_dm_avatar_prompt(7, state)
    assert ("signal" in p or "talisman" in p or "Lantern" in p)  # lore-fragment med
    assert "Dungeon Master" in p
    # Form-direktiv: arketypen får ALDRIG tvingas till human
    assert "never force it into a human" in p


def test_npc_avatar_prompt_has_form_directive():
    # En drönare ska promptas SOM drönare, aldrig tvingas till människa
    state = {"character": {}, "npcs": [{"name": "Meredith", "role": "surveillance drone in a space opera", "notes": "a sleek machine"}], "lore": []}
    p = main._build_avatar_prompt(state, "npc:Meredith")
    assert "Meredith" in p
    assert "drone" in p
    assert "never as a human" in p


def test_dm_avatar_archetypes_include_non_humanoid():
    pool = " ".join(main._DM_AVATAR_ARCHETYPES).lower()
    assert any(w in pool for w in ("drone", "nebula", "machine oracle", "swarm", "planet spirit"))


# ── Klass-specifika avatar-ledtrådar (v30) ──

def test_class_visual_cue_druid():
    cue = main._class_visual_cues("Druid")
    assert "druid" in cue.lower()
    assert "beasts" in cue or "raven" in cue or "stag" in cue

def test_class_visual_cue_subclass_matches():
    # "Druid (Circle of the Moon)" ska träffa substring-matchet
    assert main._class_visual_cues("Druid (Circle of the Moon)") != ""
    assert main._class_visual_cues("druid") != ""

def test_class_visual_cue_unknown_is_empty():
    assert main._class_visual_cues("adventurer") == ""
    assert main._class_visual_cues("") == ""
    assert main._class_visual_cues(None) == ""

def test_player_avatar_druid_gets_cue():
    state = {
        "character": {"name": "Fern", "race": "elf", "class": "Druid"},
        "inventory": [], "lore": [], "npcs": [],
    }
    p = main._build_avatar_prompt(state, "player")
    assert "wild druid" in p or "druid" in p.lower()
    assert "beasts" in p or "raven" in p or "stag" in p

def test_player_avatar_style_survives_truncation():
    """Den gamla buggen: STEP_IMAGE_STYLE låg sist och klipptes bort av
    _trim_prompt(490). Nu ligger stilen tidigt så den överlever även en
    lång story/inventory. Verifiera att porträtt-stilen finns kvar efter trim."""
    state = {
        "character": {
            "name": "Very Long Character Name Indeed",
            "race": "half-elf",
            "class": "Druid (Circle of the Moon)",
            "background": "A very long and detailed backstory about growing up in the deep forest, learning the old ways, speaking with animals, and wandering the wild places of the realm for many long years before answering the call to adventure.",
            "story": "An equally long story of travels, battles, friendships forged and lost, ancient groves tended, and a growing bond with the beasts and spirits of the land that never seems to end or repeat itself at all.",
        },
        "inventory": [{"name": "Staff"}, {"name": "Cloak"}, {"name": "Pouch"}, {"name": "Herbs"}],
        "lore": ["The forest whispers.", "Ancient omen.", "A drake circles above."],
        "npcs": [],
    }
    raw = main._build_avatar_prompt(state, "player")
    trimmed = main._trim_prompt(raw)
    assert len(trimmed) <= 490
    # Stilen måste överleva klippen
    assert "Photorealistic" in trimmed
    # Klass-ledtråden måste överleva klippen
    assert "druid" in trimmed.lower()

