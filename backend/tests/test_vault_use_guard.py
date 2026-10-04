"""Test: statusar som dicts får ALDRIG krascha chatten + valv-use-skyddet.

Bakgrund (incident 2026-10-04, spelarfeedback från chup/g_moore93):
  1) `compact_state()` gjorde `", ".join(e["statuses"])` men stridsmotorn
     skriver statusar som dicts → TypeError inuti systemprompten → hela
     POST /api/chat blev 500 och 5 kampanjer (4 spelare) blev ospelbara.
  2) `/api/vault/characters/{id}/use` skrev valv-karaktären i den AKTIVA
     kampanjen utan varning → 91 turer av Qhilvorum (niv 2) ersattes av en
     snapshot på niv 1. Nu krävs {"confirm_replace": true} för ett pågående
     äventyr, och kampanjen bär meta.vault_id så exporten uppdaterar SAMMA
     valvkort (nivå behålls, inga tvillingar).
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guardian  # noqa: E402
import main  # noqa: E402
import state_manager  # noqa: E402


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """Peka valv + kampanjer mot temporära mappar (rör aldrig skarp data)."""
    monkeypatch.setattr(state_manager, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(state_manager, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(main, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(main, "vault", state_manager.CharacterVault())
    monkeypatch.setattr(main, "store", state_manager.CampaignStore())
    return tmp_path


def _run(coro):
    return asyncio.run(coro)


def _vault_hero(user, name="The Lattice", level=1):
    return main.vault.save(
        user,
        {"name": name, "class": "Foundation", "level": level,
         "hp": {"current": 20, "max": 20}, "xp": {"current": 0, "next_level": 300}},
        campaign_name="I WIN",
        inventory=[{"name": "Bone Blade"}],
    )


def _campaign(root, user, cid, character, turns):
    cdir = root / "campaigns" / user / cid
    (cdir / "transcripts").mkdir(parents=True, exist_ok=True)
    st = {
        "meta": {"campaign_id": cid, "user": user, "campaign_name": "I WIN",
                 "turn_count": turns, "language": "en"},
        "character": character,
        "inventory": [],
    }
    (cdir / "state.json").write_text(json.dumps(st), encoding="utf-8")
    (root / "campaigns" / user / ".active_campaign").write_text(cid)
    return st


# ── 1. Statusar som dicts (500-buggen) ─────────────────────────────────

def test_compact_state_handles_dict_statuses():
    state = {
        "meta": {"campaign_name": "I WIN"},
        "character": {"name": "Qhilvorum", "class": "Wizard", "level": 2,
                      "hp": {"current": 17, "max": 27}, "ac": 20},
        "world": {"combat": {"active": True, "round": 3, "enemies": [
            {"name": "Gravehowler", "hp": 12, "max_hp": 40, "ac": 13, "alive": True,
             "statuses": [{"name": "blind", "duration": 3, "dmg_per_turn": 0}]},
            {"name": "Rot-touched Figure", "hp": 0, "max_hp": 9, "ac": 11,
             "alive": False, "statuses": [{"name": "burn", "duration": 1}]},
        ]}},
    }
    text = main.compact_state(state, "en")
    assert "Gravehowler" in text
    assert "blind" in text


def test_guardian_state_block_handles_dict_statuses():
    state = {
        "meta": {"language": "en"},
        "character": {"name": "Qhilvorum", "hp": {"current": 17, "max": 27}, "ac": 20,
                      "statuses": [{"name": "prone", "duration": 1}]},
        "world": {"combat": {"active": True, "enemies": [
            {"name": "Gravehowler", "hp": 12, "max_hp": 40, "ac": 13, "alive": True,
             "statuses": [{"name": "blind", "duration": 3}]},
        ], "allies": [
            {"name": "Vrishka", "hp": 5, "max_hp": 9, "ac": 14, "alive": True,
             "statuses": [{"name": "poison", "duration": 2}]},
        ]}},
    }
    text = guardian._format_state_for_guardian(state, "en")
    assert "blind" in text and "poison" in text and "prone" in text


# ── 2. Skyddet mot att byta ut hjälten i ett pågående äventyr ──────────

def test_use_refuses_to_replace_played_hero(tmp_store):
    from fastapi import HTTPException

    user = "chup"
    tok = main.create_token(user, "player")
    hero = _vault_hero(user)
    _campaign(tmp_store, user, "aaaa00000001",
              {"name": "Qhilvorum", "level": 2, "xp": {"current": 600},
               "updates": [{"field": "ability", "text": "Lightning Bolt"}]},
              91)

    with pytest.raises(HTTPException) as ei:
        _run(main.vault_use(hero["id"], None, tok))
    assert ei.value.status_code == 409
    # Den spelade karaktären är orörd.
    st = main.store.get(user)
    assert st["character"]["name"] == "Qhilvorum"
    assert st["character"]["level"] == 2


def test_use_allows_fresh_campaign(tmp_store):
    user = "chup"
    tok = main.create_token(user, "player")
    hero = _vault_hero(user)
    _campaign(tmp_store, user, "aaaa00000002", {"name": "Nameless", "level": 1,
                                                "hp": {"current": 10, "max": 10}}, 0)

    res = _run(main.vault_use(hero["id"], {}, tok))
    assert res["ok"] is True
    assert main.store.get(user)["character"]["name"] == "The Lattice"


def test_use_with_confirm_replaces_played_hero(tmp_store):
    user = "chup"
    tok = main.create_token(user, "player")
    hero = _vault_hero(user)
    _campaign(tmp_store, user, "aaaa00000003",
              {"name": "Qhilvorum", "level": 2, "updates": [{"field": "trait", "text": "x"}]},
              91)

    res = _run(main.vault_use(hero["id"], {"confirm_replace": True}, tok))
    assert res["ok"] is True
    assert main.store.get(user)["character"]["name"] == "The Lattice"


# ── 3. Export → samma valvkort med behållen nivå ───────────────────────

def test_use_links_vault_id_and_export_retains_level(tmp_store):
    user = "chup"
    tok = main.create_token(user, "player")
    hero = _vault_hero(user)                       # nivå 1 i valvet
    _campaign(tmp_store, user, "aaaa00000004", {"name": "Old", "level": 1}, 0)

    _run(main.vault_use(hero["id"], {}, tok))
    st = main.store.get(user)
    assert st["meta"]["vault_id"] == hero["id"]

    # Spelaren klättrar till nivå 5 …
    st["character"]["level"] = 5
    st["character"]["xp"] = {"current": 6675, "next_level": 14000}
    st["meta"]["turn_count"] = 400
    main.store.save(st)

    # … och exporterar från äventyret UTAN overwrite_id → SAMMA post, nivå 5.
    res = _run(main.vault_save({"from_campaign": True}, tok))
    assert res["overwritten"] is True
    assert res["id"] == hero["id"]
    entries = main.vault.list(user)
    assert len(entries) == 1
    assert entries[0]["character"]["level"] == 5
    assert entries[0]["character"]["xp"]["current"] == 6675


def test_export_without_link_still_allows_duplicate(tmp_store):
    """Kampanjer utan valv-länk får inte tvångsskrivas över (bakåtkompatibelt)."""
    user = "daren"
    tok = main.create_token(user, "player")
    _campaign(tmp_store, user, "aaaa00000005", {"name": "Kain", "level": 2}, 21)

    first = _run(main.vault_save({"from_campaign": True}, tok))
    second = _run(main.vault_save({"from_campaign": True}, tok))
    assert first["id"] != second["id"]
    assert len(main.vault.list(user)) == 2
