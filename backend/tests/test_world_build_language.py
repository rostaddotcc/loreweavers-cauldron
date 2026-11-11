"""Test: /api/world/build följer kampanjens språk (spelarfeedback 2026-08-11/-14).

Spelare som startade EN-kampanj fick svenska quests/NPC-roller/lore eftersom
världsextraktionen hårdkodade svenska prompts. Fixen (2026-09-07) väljer
WORLD_BUILD_PROMPT_EN / IMPORT_PROMPT_EN per kampanjspråk, MEN relation- och
quest-status-värden är kodnivå-token ("allierad|neutral|fiende|okänd", "aktiv")
som jämförs i kod — de får ALDRIG översättas.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token  # noqa: E402


@pytest.fixture
def store_tmp(tmp_path, monkeypatch):
    d = tmp_path / "campaigns"
    d.mkdir()
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def client(store_tmp):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


_EXTRACTED = {
    "locations": [{"name": "Ashen Gate", "description": "A mossy stone gate"}],
    "npcs": [{"name": "Mira", "role": "Scout", "relation": "neutral", "notes": "Quiet", "alive": True}],
    "lore": ["The gate was built by lost kings."],
    "quests": [{"name": "Light the Beacon", "description": "Climb and light it", "status": "aktiv"}],
}


def _capture_llm(monkeypatch):
    """Mocka _call_llm → fånga messages, returnera hårdkodad värld."""
    calls = []

    async def fake_llm(model_id, messages, **kw):
        calls.append(messages)
        return '{"locations": [{"name": "Ashen Gate", "description": "A mossy stone gate"}], "npcs": [{"name": "Mira", "role": "Scout", "relation": "neutral", "notes": "Quiet", "alive": true}], "lore": ["The gate was built by lost kings."], "quests": [{"name": "Light the Beacon", "description": "Climb and light it", "status": "aktiv"}]}'

    monkeypatch.setattr(main, "_call_llm", fake_llm)
    return calls


def _make_campaign(client, tok, lang):
    r = client.post("/api/campaign", json={"name": "Test", "language": lang},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    return r.json()["campaign_id"]


def test_en_campaign_gets_english_world_prompt(client, monkeypatch):
    tok = create_token("eng_player", "player")
    _make_campaign(client, tok, "en")
    calls = _capture_llm(monkeypatch)

    r = client.post("/api/world/build", data={"prompt": "A dark valley"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    assert calls, "LLM anropades inte"
    system = calls[0][0]["content"]
    assert "world-extractor" in system, "EN-kampanj fick inte den engelska världsprompten"
    assert "Bygg världen" not in calls[0][1]["content"]


def test_sv_campaign_keeps_swedish_world_prompt(client, monkeypatch):
    tok = create_token("sv_player", "player")
    _make_campaign(client, tok, "sv")
    calls = _capture_llm(monkeypatch)

    r = client.post("/api/world/build", data={"prompt": "En mörk dal"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    system = calls[0][0]["content"]
    assert "världsextraktor" in system


def test_explicit_language_form_param_overrides(client, monkeypatch):
    """Form-fältet language styr även om kampanjen är SV (CLI/annan client)."""
    tok = create_token("ovr_player", "player")
    _make_campaign(client, tok, "sv")
    calls = _capture_llm(monkeypatch)
    r = client.post("/api/world/build",
                    data={"prompt": "A dark valley", "language": "en"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    assert "world-extractor" in calls[0][0]["content"]


def test_created_quests_keep_code_token_status(client, monkeypatch):
    """Quest status 'aktiv' är kodnivå — bevaras i båda språken."""
    tok = create_token("tok_player", "player")
    cid = _make_campaign(client, tok, "en")
    _capture_llm(monkeypatch)
    r = client.post("/api/world/build", data={"prompt": "x", "language": "en"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    state = main.store.get("tok_player", cid)
    quests = state.get("quests", [])
    assert quests and quests[0]["status"] in ("aktiv", "active")


def test_merge_defaults_english_role_for_en_campaign(client, monkeypatch):
    """NPC utan role i EN-kampanj → 'unknown', inte 'okänd' (textinnehåll)."""
    tok = create_token("role_player", "player")
    cid = _make_campaign(client, tok, "en")

    async def fake_llm(model_id, messages, **kw):
        return '{"locations": [], "npcs": [{"name": "Sly", "relation": "neutral"}], "lore": [], "quests": []}'

    monkeypatch.setattr(main, "_call_llm", fake_llm)
    r = client.post("/api/world/build", data={"prompt": "x", "language": "en"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200
    state = main.store.get("role_player", cid)
    npc = next(n for n in state["npcs"] if n["name"] == "Sly")
    assert npc["role"] == "unknown"
