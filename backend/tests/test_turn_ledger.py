"""Turn-ledger (2026-08-08) — 1 turn per prompt.

Täcker:
  - en chat-turn kostar EXAKT EN turn (action="dm"); Guardian pre/post,
    faktaextraktion och alla bakgrundsanrop INGÅR i den turnen och bokförs
    inte separat i turn-ledgern (backend/data/turn_ledgers/<user>.jsonl)
  - ledger-åtgärder: dm (chat), image, tts, char_gen, search, repair,
    chapter, logbook
  - admin-endpointen /api/admin/user/{username}/ledger returnerar posterna
  - bildgenerering bokför action=image

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger mot tmp —
ALDRIG riktig data.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture
def llm_mocks(monkeypatch):
    async def fake_dm(model_id, messages, **kw):
        return ("The wind howls.", "", {"total_tokens": 42})

    async def noop(*a, **k):
        return None

    async def no_memory(*a, **k):
        return {"text": "", "facts_sent": 0, "rag_sent": 0, "timing_s": 0.0}

    monkeypatch.setattr(main, "_call_llm_with_reasoning", fake_dm)
    monkeypatch.setattr(main, "guardian_check_roll", noop)
    monkeypatch.setattr(main, "_retrieve_relevant_memory", no_memory)
    monkeypatch.setattr(main, "_guardian_post_dm", noop)
    monkeypatch.setattr(main, "_post_turn_tasks", noop)


@pytest.fixture
def client(users_file, campaigns_dir, turn_ledgers_dir, ledger_file, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _register(client, username="alice", password="secret123"):
    r = client.post("/api/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


def _user(username="alice") -> dict:
    return main.load_users().get(username, {})


def _patch_user(username, **fields):
    users = main.load_users()
    u = users.setdefault(username, {})
    u.update(fields)
    main.save_users(users)


def _make_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def _chat(client, message="Hej där!", model="step-3.7-flash"):
    return client.post("/api/chat", json={"message": message, "model_id": model})


def _admin_token():
    users = main.load_users()
    users["the_admin"] = {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0}
    main.save_users(users)
    return create_token("the_admin", "admin")


def test_chat_consumes_one_turn_and_ledgers_dm(client):
    _register(client)
    _make_campaign("alice")
    r = _chat(client)
    assert r.status_code == 200, r.text
    # 1 turn per prompt: ingen startbonus mer (borttagen 2026-09-06) —
    # första turen äter cap-sloten direkt.
    assert _user()["promo_bonus"] == 0
    assert _user()["turns_used"] == 1
    entries = main._read_turn_ledger("alice")
    actions = [e["action"] for e in entries]
    assert actions == ["dm"], actions
    for e in entries:
        assert e.get("ts") and e.get("model") == "step-3.7-flash"


def test_ledger_records_one_dm_turn_even_on_even_turn(client):
    _register(client)
    _make_campaign("alice")
    # Jämn turn (effective_turn 10) — extraction/threads är due i pipelinen
    # men INGÅR i meddelandets enda turn och bokförs inte separat.
    st = main.store.get("alice")
    assert st is not None
    st["meta"]["turn_count"] = 9
    main.store.save(st)
    r = _chat(client)
    assert r.status_code == 200, r.text
    actions = [e["action"] for e in main._read_turn_ledger("alice")]
    assert actions == ["dm"], actions


def test_admin_ledger_endpoint(client):
    _register(client)
    _make_campaign("alice")
    _chat(client)
    atok = _admin_token()
    r = client.get("/api/admin/user/alice/ledger", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) == 1
    assert body["breakdown_all"]["dm"]["turns"] == 1
    # Spelaren får ALDRIG se ledgern
    r2 = client.get("/api/admin/user/alice/ledger")
    assert r2.status_code in (401, 403)


def test_admin_user_detail_includes_ledger(client):
    _register(client)
    _make_campaign("alice")
    _chat(client)
    atok = _admin_token()
    r = client.get("/api/admin/user/alice", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "turn_ledger" in body
    assert "turn_ledger_today" in body
    assert body["turn_ledger"]["dm"]["turns"] >= 1
