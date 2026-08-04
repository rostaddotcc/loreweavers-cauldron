"""Security hardening 2026-08-04 (audit P1) — login rate-limit + char-gen turn.

autouse-fixtures: users.json pekas mot tmp — rör ALDRIG riktiga data.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
from auth import hash_password  # noqa: E402


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    """Peka users.json mot tmp-fil — autouse så inget test rör riktiga data."""
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    # In-memory rate-limits får inte läcka mellan tester.
    main._LOGIN_FAILS.clear()
    main._DIRECT_RESET_TIMES.clear()
    return f


@pytest.fixture(autouse=True)
def campaigns_dir(tmp_path, monkeypatch):
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", password="secret123", turn_cap=50, turns_used=0):
    # reset_date i framtiden → lazy period-rollover nollställer inte kvoten.
    reset_date = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    main.save_users({username: {
        "password_hash": hash_password(password), "role": "player",
        "turn_cap": turn_cap, "turns_used": turns_used, "turn_bonus": 0,
        "reset_date": reset_date, "subscription_status": "free",
        "subscription_until": None,
    }})


# ── Login brute-force-lås ────────────────────────────────────────────────

def test_login_locks_after_10_failures(client):
    _seed()
    for _ in range(10):
        r = client.post("/api/login", json={"username": "alice", "password": "wrong"})
        assert r.status_code == 401
    # 11:e försöket (även med RÄTT lösenord) → låst
    r = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 429
    assert "Too many login attempts" in r.json()["detail"]


def test_login_success_resets_failures(client):
    _seed()
    for _ in range(9):
        assert client.post("/api/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    # Rätt lösenord på 10:e försöket → OK + räknaren nollställs
    assert client.post("/api/login", json={"username": "alice", "password": "secret123"}).status_code == 200
    # Ett nytt fel räcker inte för att låsa
    assert client.post("/api/login", json={"username": "alice", "password": "wrong"}).status_code == 401


def test_login_unknown_user_also_rate_limited(client):
    """Även icke-existerande användarnamn låses (förhindrar enumerering via låset)."""
    for _ in range(10):
        client.post("/api/login", json={"username": "ghost", "password": "x"})
    r = client.post("/api/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 429


# ── Karaktärsgenerering förbrukar turn ───────────────────────────────────

@pytest.fixture
def llm_mock(monkeypatch):
    async def fake_call_llm(model_id, messages, **kw):
        return json.dumps({
            "name": "Testarion", "race": "Human", "class": "Fighter",
            "alignment": "Neutral", "background": "Soldier", "level": 1,
            "abilities": {"str": 15, "dex": 12, "con": 14, "int": 10, "wis": 11, "cha": 9},
        })
    monkeypatch.setattr(main, "_call_llm", fake_call_llm)


def _make_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def _login(client, username="alice", password="secret123"):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


def test_character_generation_consumes_a_turn(client, llm_mock):
    _seed()
    _make_campaign("alice")
    _login(client)
    assert main.load_users()["alice"]["turns_used"] == 0
    r = client.post("/api/character/generate", json={"prompt": "A grizzled veteran", "model_id": "step-3.7-flash"})
    assert r.status_code == 200, r.text
    assert main.load_users()["alice"]["turns_used"] == 1


def test_character_generation_blocked_when_no_turns(client, llm_mock):
    _seed(turn_cap=5, turns_used=5)  # kvot slut
    _make_campaign("alice")
    _login(client)
    r = client.post("/api/character/generate", json={"prompt": "A grizzled veteran", "model_id": "step-3.7-flash"})
    assert r.status_code == 403
    data = r.json()
    assert data.get("detail", {}).get("cap_reached") is True
    # Ingen turn förbrukades (redan på max)
    assert main.load_users()["alice"]["turns_used"] == 5
