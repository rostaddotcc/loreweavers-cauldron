"""Test: exportera kampanjkaraktär till The Forge — overwrite-stöd.

POST /api/vault/characters {from_campaign: true} sparar den aktiva kampanjens
karaktär + inventory i valvet. Med overwrite_id uppdateras den befintliga
posten (samma id — ingen duplikat); utan overwrite_id skapas en ny post
(duplicering är tillåten).
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import state_manager  # noqa: E402


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    """Peka vault- och kampanjlagring mot temporära mappar."""
    monkeypatch.setattr(state_manager, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(state_manager, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path / "campaigns")
    monkeypatch.setattr(main, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(main, "vault", state_manager.CharacterVault())
    monkeypatch.setattr(main, "store", state_manager.CampaignStore())
    return tmp_path


def _make_campaign(root, user, cid, name, level):
    cdir = root / "campaigns" / user / cid
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "transcripts").mkdir(exist_ok=True)
    state = {
        "meta": {
            "campaign_id": cid,
            "user": user,
            "campaign_name": "The Long Road",
            "turn_count": 12,
            "session_count": 1,
        },
        "character": {
            "name": name,
            "class": "Warlock",
            "level": level,
            "hp": {"max": 44},
        },
        "inventory": [{"name": "Bone Blade"}],
    }
    (cdir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (root / "campaigns" / user / ".active_campaign").write_text(cid)
    return state


def _run(coro):
    return asyncio.run(coro)


def test_export_creates_vault_entry(tmp_vault):
    user = "zagreus"
    token = main.create_token(user, "player")
    _make_campaign(tmp_vault, user, "c1", "Thalindra", 3)

    res = _run(main.vault_save({"from_campaign": True}, token))
    assert res["ok"] is True
    assert res["overwritten"] is False

    entries = main.vault.list(user)
    assert len(entries) == 1
    assert entries[0]["character"]["name"] == "Thalindra"
    assert entries[0]["inventory"][0]["name"] == "Bone Blade"
    assert entries[0]["campaign_name"] == "The Long Road"


def test_export_overwrite_keeps_same_id(tmp_vault):
    user = "nyx"
    token = main.create_token(user, "player")
    _make_campaign(tmp_vault, user, "c1", "Thalindra", 3)

    first = _run(main.vault_save({"from_campaign": True}, token))
    assert first["overwritten"] is False

    # Karaktären växer (level 5) → andra export med overwrite_id
    _make_campaign(tmp_vault, user, "c1", "Thalindra", 5)
    second = _run(main.vault_save({"from_campaign": True, "overwrite_id": first["id"]}, token))
    assert second["overwritten"] is True
    assert second["id"] == first["id"]  # samma post, ingen duplikat

    entries = main.vault.list(user)
    assert len(entries) == 1
    assert entries[0]["character"]["level"] == 5


def test_export_without_overwrite_allows_duplicate(tmp_vault):
    user = "morpheus"
    token = main.create_token(user, "player")
    _make_campaign(tmp_vault, user, "c1", "Kain", 2)

    _run(main.vault_save({"from_campaign": True}, token))
    _run(main.vault_save({"from_campaign": True}, token))  # ingen overwrite_id

    assert len(main.vault.list(user)) == 2
