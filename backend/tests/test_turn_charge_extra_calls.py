"""Samtliga LLM-anrop räknas som turns (2026-08-08).

Före: active threads (var 10:e tur), kapitel-sammanfattning (trigger_chapter),
loggboken (första besöket) och dag-entry-uppdateringen (refresh-today) gjorde
`_call_llm` UTAN att dra en turn — gratis LLM-anrop.

Nu: allt räknas.
- active threads: `_consume_turn_if_available` (skippas tyst vid 0, som
  dag-entry — ett bakgrundsanrop får aldrig kasta)
- chapter/logbook/refresh-today: `_gate_turn_quota` + `_consume_turn`
  (403 cap_reached vid 0)

autouse-fixtures: ALLA tester pekar users.json + kampanjer + turn-ledger
mot tmp — ALDRIG riktig data.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def campaigns_dir(tmp_path, monkeypatch):
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def turn_ledgers_dir(tmp_path, monkeypatch):
    """Peka turn-ledgern mot tmp — annars skriver testerna riktiga filer."""
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


# LLM-svar som testerna kan byta per test (stubbar _call_llm, inget nätverk)
FAKE_LLM = {"response": "{}"}


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    async def _fake(model, messages, **kwargs):
        return FAKE_LLM["response"]
    monkeypatch.setattr(main, "_call_llm", _fake)
    # Bakgrundssammanfattningar aldrig "dags" i dessa tester
    monkeypatch.setattr(main.store, "maybe_summarize", lambda st: False)
    monkeypatch.setattr(main.store, "maybe_chapter", lambda st: False)
    monkeypatch.setattr(main.store, "maybe_arc", lambda st: False)
    # Qdrant nere → RAG-indexering skippas i post-turn-pipelinen
    async def _healthy():
        return False
    monkeypatch.setattr(main.rag, "qdrant_healthy", _healthy)


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", used=0):
    u = {"password_hash": hash_password("secret123"), "role": role,
         "turn_cap": 50, "turns_used": used, "turn_bonus": 0, "promo_bonus": 0,
         "start_bonus_granted": True,
         "reset_date": "2099-01-01", "subscription_status": "free",
         "subscription_until": None,
         "features": {"export": True},
         "features_until": "2099-01-01",
         "wan_used_today": 0, "wan_reset_date": None,
         "created_at": "2026-08-01T10:00:00+00:00",
         "last_login": "2026-08-04T09:00:00+00:00"}
    main.save_users({username: u})


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _seed_campaign(username):
    st = main.store.create(username, name="Test Campaign", language="en")
    return st["meta"]["campaign_id"]


def _append_transcript(username, campaign_id, n=25):
    """Lägg in n transkript-meddelanden så LLM-vägar triggas."""
    st = main.store.get(username, campaign_id)
    for i in range(n):
        main.store.append_message(
            st, "player" if i % 2 == 0 else "dm",
            f"Message {i}: the party explores the dark halls.", {"turn": i + 1},
        )
    return st


# ═══════════════ Kapitel-sammanfattning (/api/campaign/chapter) ═══════════════

def test_chapter_trigger_consumes_one_turn(client):
    _seed("alice")
    _seed_campaign("alice")
    tok = _tok()
    FAKE_LLM["response"] = "Kapitel ett: äventyret börjar i mörkret."

    r = client.post("/api/campaign/chapter", json={"title": "Kapitel 1"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    assert auth.load_users()["alice"]["turns_used"] == 1


def test_chapter_trigger_403_when_zero_turns(client):
    _seed("alice", used=50)  # cap 50/50 förbrukad → 0 kvar
    _seed_campaign("alice")
    tok = _tok()

    r = client.post("/api/campaign/chapter", json={"title": "Kapitel 1"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["cap_reached"] is True
    assert auth.load_users()["alice"]["turns_used"] == 50  # ingen konsumtion


# ═══════════════ Loggbok (/api/campaign/logbook) ═══════════════

def test_logbook_first_visit_consumes_one_turn_then_cached(client):
    _seed("alice")
    cid = _seed_campaign("alice")
    _append_transcript("alice", cid)
    tok = _tok()
    FAKE_LLM["response"] = '{"title": "Test", "days": [{"day": 1, "title": "Dag 1", "events": ["e"]}]}'

    r1 = client.get("/api/campaign/logbook", cookies={"morkrets_token": tok})
    assert r1.status_code == 200, r1.text
    assert auth.load_users()["alice"]["turns_used"] == 1

    # Andra besöket: cachad → gratis (ingen ny turn)
    r2 = client.get("/api/campaign/logbook", cookies={"morkrets_token": tok})
    assert r2.status_code == 200, r2.text
    assert auth.load_users()["alice"]["turns_used"] == 1


def test_logbook_403_when_zero_turns(client):
    _seed("alice", used=50)
    cid = _seed_campaign("alice")
    _append_transcript("alice", cid)
    tok = _tok()

    r = client.get("/api/campaign/logbook", cookies={"morkrets_token": tok})
    assert r.status_code == 403
    assert r.json()["detail"]["cap_reached"] is True
    assert auth.load_users()["alice"]["turns_used"] == 50


# ═══════════════ Dag-entry-uppdatering (/api/campaign/logbook/refresh-today) ═══════════════

def test_refresh_today_consumes_one_turn(client):
    _seed("alice")
    cid = _seed_campaign("alice")
    st = _append_transcript("alice", cid)
    # Cacha en dag-entry så endpointen har något att regenerera
    st["world"].setdefault("logbook_llm", {})["days"] = [
        {"day": 1, "title": "Gammal", "events": ["x"]}
    ]
    st["world"]["last_day_turn"] = 0
    main.store.save(st)
    tok = _tok()
    FAKE_LLM["response"] = '{"day": 1, "title": "Ny dag", "mood": "spänd", "events": ["e"]}'

    r = client.post("/api/campaign/logbook/refresh-today",
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    assert auth.load_users()["alice"]["turns_used"] == 1


def test_refresh_today_403_when_zero_turns(client):
    _seed("alice", used=50)
    cid = _seed_campaign("alice")
    st = _append_transcript("alice", cid)
    st["world"].setdefault("logbook_llm", {})["days"] = [
        {"day": 1, "title": "Gammal", "events": ["x"]}
    ]
    st["world"]["last_day_turn"] = 0
    main.store.save(st)
    tok = _tok()

    r = client.post("/api/campaign/logbook/refresh-today",
                    cookies={"morkrets_token": tok})
    assert r.status_code == 403
    assert r.json()["detail"]["cap_reached"] is True
    assert auth.load_users()["alice"]["turns_used"] == 50


# ═══════════════ Active threads (post-turn-pipelinen, var 10:e tur) ═══════════════

def test_threads_update_is_free_and_saves_threads():
    """Threads är en intern bakgrundsuppgift — INGÅR i meddelandets turn (gratis)."""
    _seed("alice")
    cid = _seed_campaign("alice")
    _append_transcript("alice", cid)
    FAKE_LLM["response"] = (
        '[{"name": "Hildas uppdrag", "status": "active", "last_turn": 10, '
        '"summary": "Hitta kartan"}]'
    )

    import asyncio
    asyncio.run(main._post_turn_tasks_locked(
        "alice", cid, "reply", "player msg", turn_count=10, model_id="step-3.7-flash"
    ))

    users = auth.load_users()
    assert users["alice"]["turns_used"] == 0  # inga separata turns för threads
    # Threads sparades ändå i state
    st = main.store.get("alice", cid)
    assert st["meta"].get("active_threads", [])[0]["name"] == "Hildas uppdrag"


def test_threads_update_runs_even_at_zero_turns():
    """Threads är gratis internt — körs även vid 0 turns (kastar aldrig)."""
    _seed("alice", used=50)  # cap 50/50 → 0 kvar
    cid = _seed_campaign("alice")
    _append_transcript("alice", cid)
    FAKE_LLM["response"] = '[{"name": "Tråd", "status": "active", "last_turn": 10, "summary": "s"}]'

    import asyncio
    asyncio.run(main._post_turn_tasks_locked(
        "alice", cid, "reply", "player msg", turn_count=10, model_id="step-3.7-flash"
    ))

    users = auth.load_users()
    assert users["alice"]["turns_used"] == 50  # oförändrad — inget kast, ingen konsumtion
    st = main.store.get("alice", cid)
    assert st["meta"].get("active_threads", [])[0]["name"] == "Tråd"  # kördes ändå
