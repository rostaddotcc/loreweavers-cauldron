"""Undo en tur (2026-09-09) — ångra senaste prompten + allt storyn skrev.

Täcker:
  - snapshot tas FÖRE varje chat-tur (single-level)
  - undo återställer state.json, facts.json, transkript och summaries
  - undo kostar EXAKT en turn (action="undo") och bokförs i turn-ledgern
  - undo utan snapshot → 409, dubbel-undo → 409 (kostar ingen extra turn)
  - turn-tak → 403 med cap_reached
  - /guardian tar ingen snapshot (korrigeringsverktyg, ingen story-tur)
  - LLM-fel före commit → snapshotet slängs (inget att ångra)
  - epoch-guard: bakgrundspipelinen avbryter om turen hunnit ångras
  - /api/campaign/transcript exponerar undo_available
  - path traversal i campaign_id avvisas

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger mot tmp —
ALDRIG riktig data.
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import extraction  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from extraction import Fact, FactRegister  # noqa: E402


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
    # Faktaregistret (extraction.py) har EGNA sökvägs-globaler — utan denna
    # pekare skriver FactRegister till riktig backend/data (testläckage).
    monkeypatch.setattr(extraction, "_CAMPAIGNS_DIR", d)
    monkeypatch.setattr(extraction, "_DATA_DIR", tmp_path)
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
        return ("The wind howls.", "", {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42})

    async def noop(*a, **k):
        return None

    async def no_memory(*a, **k):
        return {"text": "", "facts_sent": 0, "rag_sent": 0, "timing_s": 0.0}

    monkeypatch.setattr(main, "_call_llm_with_reasoning", fake_dm)
    monkeypatch.setattr(main, "guardian_check_roll", noop)
    monkeypatch.setattr(main, "_retrieve_relevant_memory", no_memory)
    monkeypatch.setattr(main, "_guardian_post_dm", noop)
    monkeypatch.setattr(main, "_post_turn_tasks", noop)

    async def no_qdrant():
        return False

    monkeypatch.setattr(main.rag, "qdrant_healthy", no_qdrant)


@pytest.fixture
def client(users_file, campaigns_dir, turn_ledgers_dir, ledger_file, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── helpers ──────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _seed_user(username="alice", role="player", turn_cap=50) -> str:
    """Seeda användare DIREKT — /api/register är rate-limitad process-globalt
    (_REGISTER_TIMES) och ger 429 i helsviten (test-isolation-pitfall)."""
    users = main.load_users()
    users[username] = {
        "password_hash": hash_password("secret123"), "role": role,
        "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
        "promo_bonus": 0, "reset_date": _today(), "subscription_status": "free",
        "start_bonus_granted": True,
    }
    main.save_users(users)
    return create_token(username, role)


def _login(client, username="alice", role="player") -> str:
    tok = _seed_user(username, role)
    client.cookies.set("morkrets_token", tok)
    return tok


def _user(username="alice") -> dict:
    return main.load_users().get(username, {})


def _patch_user(username, **fields):
    users = main.load_users()
    u = users.setdefault(username, {})
    u.update(fields)
    main.save_users(users)


def _make_campaign(username="alice"):
    return main.store.create(username, name="Test Campaign", language="en")


def _chat(client, message="Hej där!", model="step-3.7-flash"):
    return client.post("/api/chat", json={"message": message, "model_id": model})


def _cid(username="alice") -> str:
    return main.store.get(username)["meta"]["campaign_id"]


def _add_fact(username, fact_id, text, turn=0):
    reg = FactRegister(username, _cid(username))
    reg.add_facts([Fact(id=fact_id, category="npc", text=text, source_turn=turn)])


def _fact_ids(username):
    return sorted(f.id for f in FactRegister(username, _cid(username))._facts)


def _summary_names(username):
    d = main.store._summaries_dir(username, _cid(username))
    return sorted(p.name for p in d.glob("*.json")) if d.exists() else []


# ── tester ───────────────────────────────────────────────

def test_undo_restores_state_facts_transcript_and_summaries(client):
    _login(client)
    _make_campaign("alice")

    st = main.store.get("alice")
    st["character"]["hp"] = {"current": 20, "max": 20}
    st["inventory"] = [{"id": "i1", "name": "Sword", "qty": 1}]
    main.store.save(st)
    _add_fact("alice", "f1", "The innkeeper is called Vela")
    main.store.save_summary(main.store.get("alice"), "old scene")

    assert _chat(client).status_code == 200

    # Efter turen: simulera Guardian + faktextraktion (muterar state/facts/summaries)
    st2 = main.store.get("alice")
    st2["character"]["hp"]["current"] = 3
    st2["inventory"].append({"id": "loot", "name": "Rusty key", "qty": 1})
    st2.setdefault("npcs", []).append({"name": "Zombie", "status": "alive"})
    main.store.save(st2)
    _add_fact("alice", "f2", "A wrong fact", turn=1)
    main.store.save_summary(main.store.get("alice"), "new scene")
    assert len(main.store.load_transcript(main.store.get("alice"))) == 2

    r = client.post("/api/campaign/undo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed_messages"] == 2
    assert body["removed_summaries"] == 1
    assert body["turn_count"] == 0

    st3 = main.store.get("alice")
    assert st3["meta"]["turn_count"] == 0
    assert st3["character"]["hp"]["current"] == 20
    assert not any(i["name"] == "Rusty key" for i in st3["inventory"])
    assert not any(n.get("name") == "Zombie" for n in st3.get("npcs", []))
    assert main.store.load_transcript(st3) == []
    assert _fact_ids("alice") == ["f1"]
    assert _summary_names("alice") == ["summary-turn-0000.json"]


def test_undo_costs_one_turn_and_is_ledgered(client):
    _login(client)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    assert _user()["turns_used"] == 1

    r = client.post("/api/campaign/undo")
    assert r.status_code == 200, r.text
    assert _user()["turns_used"] == 2
    assert r.json()["turns_left"] == main._turns_available("alice")

    actions = [e["action"] for e in main._read_turn_ledger("alice")]
    assert actions == ["dm", "undo"], actions


def test_undo_without_snapshot_and_double_undo_return_409(client):
    _login(client)
    _make_campaign("alice")

    r = client.post("/api/campaign/undo")
    assert r.status_code == 409, r.text
    assert "Nothing to undo" in r.json()["detail"]
    assert _user().get("turns_used", 0) == 0  # ingen turn debiterad

    assert _chat(client).status_code == 200
    assert client.post("/api/campaign/undo").status_code == 200
    r2 = client.post("/api/campaign/undo")
    assert r2.status_code == 409
    assert _user()["turns_used"] == 2  # chat + undo, inte den misslyckade


def test_undo_blocked_by_turn_cap(client):
    _login(client)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    _patch_user("alice", turn_cap=1, turns_used=1, promo_bonus=0, turn_bonus=0)

    r = client.post("/api/campaign/undo")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["cap_reached"] is True
    # Läget är orört — ingen turn drogs, ingen återställning gjordes
    assert main.store.get("alice")["meta"]["turn_count"] == 1
    assert main.store.undo_available(main.store.get("alice")) is True


def test_guardian_command_does_not_take_snapshot(client, monkeypatch):
    _login(client)
    _make_campaign("alice")

    async def fake_guardian(instruction, state, username, call, language="en"):
        return "🛡️ fixed the record"

    monkeypatch.setattr(main, "_guardian_manual_correction", fake_guardian)
    r = _chat(client, "/guardian fix my inventory")
    assert r.status_code == 200, r.text
    assert "fixed the record" in r.json()["reply"]
    assert main.store.undo_available(main.store.get("alice")) is False


def test_llm_failure_discards_snapshot(client, monkeypatch):
    _login(client)
    _make_campaign("alice")

    async def boom(*a, **k):
        raise ValueError("provider down")

    monkeypatch.setattr(main, "_call_llm_with_reasoning", boom)
    r = _chat(client)
    assert r.status_code == 502, r.text
    assert main.store.undo_available(main.store.get("alice")) is False


def test_epoch_guard_blocks_stale_background_save(client):
    _login(client)
    _make_campaign("alice")
    st = main.store.get("alice")
    cid = st["meta"]["campaign_id"]

    assert main._epoch_ok("alice", cid, None) is True
    assert main._epoch_ok("alice", cid, int(st["meta"].get("epoch", 0) or 0)) is True
    assert main._epoch_ok("alice", cid, 999) is False

    st["meta"]["epoch"] = 1
    main.store.save(st)
    assert main._epoch_ok("alice", cid, 0) is False
    assert main._epoch_ok("alice", cid, 1) is True


def test_post_turn_pipeline_aborts_after_undo(client):
    """Turn 20 skulle trigga en scen-sammanfattning — men epoken är död."""
    _login(client)
    _make_campaign("alice")
    cid = _cid("alice")

    asyncio.run(main._post_turn_tasks_locked(
        "alice", cid, "reply", "msg", 20, "step-3.7-flash", epoch=999,
    ))
    assert _summary_names("alice") == []


def test_transcript_exposes_undo_available(client):
    _login(client)
    _make_campaign("alice")

    assert client.get("/api/campaign/transcript").json()["undo_available"] is False
    assert _chat(client).status_code == 200
    assert client.get("/api/campaign/transcript").json()["undo_available"] is True
    assert client.post("/api/campaign/undo").status_code == 200
    assert client.get("/api/campaign/transcript").json()["undo_available"] is False


def test_snapshot_is_single_level(client):
    _login(client)
    _make_campaign("alice")
    assert _chat(client, "first action").status_code == 200
    assert _chat(client, "second action").status_code == 200

    body = client.post("/api/campaign/undo").json()
    assert body["turn_count"] == 1
    assert body["undo_prompt"] == "second action"


def test_restore_rejects_path_traversal_campaign_id(client):
    _login(client)
    _make_campaign("alice")
    assert main.store.restore_turn("alice", "../../etc") is None
    assert main.store.undo_available(
        {"meta": {"user": "alice", "campaign_id": "../../etc"}}
    ) is False


def test_other_user_without_campaign_cannot_undo(client):
    _login(client, "alice")
    _make_campaign("alice")
    assert _chat(client).status_code == 200

    # bob loggar in i samma TestClient (cookie byts) och har ingen kampanj
    _login(client, "bob")
    r = client.post("/api/campaign/undo")
    assert r.status_code == 404
    # alices snapshot är orört
    users = main.load_users()
    users["alice"].setdefault("turn_cap", 0)
    main.save_users(users)
    assert main.store.undo_available(main.store.get("alice")) is True


def test_admin_can_see_undo_in_ledger(client):
    _login(client)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    assert client.post("/api/campaign/undo").status_code == 200

    users = main.load_users()
    users["the_admin"] = {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0}
    main.save_users(users)
    atok = create_token("the_admin", "admin")
    r = client.get("/api/admin/user/alice/ledger", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    assert r.json()["breakdown_all"]["undo"]["turns"] == 1
