"""FAS A: free account system — periodbaserad turn-räkning, tier, modellgating.

Täcker:
  - register skapar free-fält (turns_used/turn_bonus/reset_date/subscription_*)
  - admin-create skapar samma fält
  - turns_used ökar per godkänd chat-turn (och /api/me speglar det)
  - 403 + cap_reached/reset_date när periodens turns är slut
  - reset_date-rollover (turns_used nollställs, turn_bonus behålls, +30 dagar)
  - turn_bonus förbrukas före cap-turns
  - free-tier → modellen klampas alltid till step-3.7-flash
  - premium → vald modell behålls + oändliga turns
  - utgången premium demote:as till free
  - legacy-konton utan FAS A-fält backfillas via setdefault

Ingen riktig data rörs: users.json pekas om till tmp (auth.USERS_FILE) och
kampanj-data till tmp (state_manager.CAMPAIGNS_DIR + main.CAMPAIGNS_DIR).
LLM/RAG/bakgrundsanrop mockas bort.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    """Peka users.json mot tmp-fil (load_users/save_users i auth.py).

    autouse: ALLA tester i denna modul skyddas — även de som anropar
    seed-helpers utan att be om fixturen. Utan autouse skrev testerna
    över den RIKTIGA users.json (bugg 2026-08-04).
    """
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture
def campaigns_dir(tmp_path, monkeypatch):
    """Peka kampanj-data mot tmp-mapp (state_manager + main)."""
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def llm_mocks(monkeypatch):
    """Inga riktiga LLM/RAG/bakgrundsanrop i chat-testerna."""
    calls = {"models": []}

    async def fake_dm(model_id, messages, **kw):
        calls["models"].append(model_id)
        return ("The wind howls through the pines.", "", {"total_tokens": 42})

    async def noop(*a, **k):
        return None

    async def no_memory(*a, **k):
        return ""

    monkeypatch.setattr(main, "_call_llm_with_reasoning", fake_dm)
    monkeypatch.setattr(main, "guardian_check_roll", noop)
    monkeypatch.setattr(main, "_retrieve_relevant_memory", no_memory)
    monkeypatch.setattr(main, "_guardian_post_dm", noop)
    monkeypatch.setattr(main, "_post_turn_tasks", noop)
    return calls


@pytest.fixture
def client(users_file, campaigns_dir, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── Hjälpare ─────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


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


# ── Register / admin-create skapar free-fält ─────────────────────────────

def test_register_creates_free_fields(client):
    _register(client)
    u = _user()
    assert u["turn_cap"] == main.DEFAULT_TURN_CAP
    assert u["turns_used"] == 0
    assert u["turn_bonus"] == 0
    assert u["reset_date"] == _today()
    assert u["subscription_status"] == "free"
    assert u["subscription_until"] is None


def test_admin_create_adds_free_fields(client):
    main.save_users({
        "the_admin": {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0},
    })
    atok = create_token("the_admin", "admin")
    r = client.post(
        "/api/admin/user",
        json={"username": "charlie", "password": "secret123"},
        cookies={"morkrets_token": atok},
    )
    assert r.status_code == 200, r.text
    u = _user("charlie")
    assert u["turns_used"] == 0
    assert u["turn_bonus"] == 0
    assert u["reset_date"] == _today()
    assert u["subscription_status"] == "free"
    assert u["subscription_until"] is None


# ── Turn-räkning ─────────────────────────────────────────────────────────

def test_turns_used_increments(client):
    _register(client)
    _make_campaign("alice")
    r = _chat(client)
    assert r.status_code == 200, r.text
    assert _user()["turns_used"] == 1
    # /api/me speglar period-räkningen
    me = client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["turns_used"] == 1
    assert body["turns_available"] == main.DEFAULT_TURN_CAP - 1


def test_cap_reached_403(client):
    _register(client)
    _make_campaign("alice")
    _patch_user("alice", turn_cap=1, turn_bonus=0)
    r1 = _chat(client)
    assert r1.status_code == 200, r1.text
    r2 = _chat(client)
    assert r2.status_code == 403
    detail = r2.json()["detail"]
    assert detail["cap_reached"] is True
    assert detail["reset_date"]  # ej tom — frontend visar modal med datum
    assert "message" in detail


def test_me_returns_free_fields(client):
    _register(client)
    until = _in_days(30)
    _patch_user("alice", turn_bonus=3, subscription_status="premium", subscription_until=until)
    me = client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    for key in ("turns_used", "turn_bonus", "reset_date", "subscription_status",
                "subscription_until", "turns_available"):
        assert key in body, f"missing /api/me field: {key}"
    assert body["turn_bonus"] == 3
    assert body["subscription_status"] == "premium"
    assert body["subscription_until"] == until
    assert body["turns_available"] == 999999


# ── Reset-rollover ───────────────────────────────────────────────────────

def test_reset_date_rollover(client):
    _register(client)
    _patch_user("alice", turns_used=5, turn_bonus=7, turn_cap=50, reset_date=_in_days(-1))
    avail = main._turns_available("alice")
    assert avail == 57  # nollställd (50 cap) + bonus behållen (7)
    u = _user()
    assert u["turns_used"] == 0
    assert u["turn_bonus"] == 7          # bonus behålls över rollover
    assert u["reset_date"] == _in_days(1)  # flyttad till idag + 1 (daglig rollover)


def test_turn_bonus_consumed_first(client):
    _register(client)
    _patch_user("alice", turn_cap=1, turn_bonus=100, turns_used=0)
    # 0 förbrukade: hela bonusen + cap-sloten
    assert main._turns_available("alice") == 101
    # 1 förbrukad: bonusen är orörd (100) — cap-sloten förbrukades
    _patch_user("alice", turns_used=1)
    assert main._turns_available("alice") == 100
    # Bonusen tar slut också: efter 101 förbrukade → 0 → 403
    _patch_user("alice", turns_used=101)
    assert main._turns_available("alice") == 0


# ── Modellgating ─────────────────────────────────────────────────────────

def test_free_model_clamp(client, llm_mocks):
    _register(client)
    _make_campaign("alice")
    r = _chat(client, model="qwen3.8-max")
    assert r.status_code == 200, r.text
    # DM-anropet fick den klampade modellen
    assert llm_mocks["models"] == ["step-3.7-flash"]
    # och hjälpfunktionen direkt
    assert main._clamp_player_model("qwen3.8-max", tier="free") == "step-3.7-flash"
    assert main._clamp_player_model("qwen3.8-max", tier=main._tier_for("alice")) == "step-3.7-flash"


def test_premium_model_ok(client, llm_mocks):
    _register(client)
    _make_campaign("alice")
    _patch_user("alice", subscription_status="premium", subscription_until=_in_days(30))
    r = _chat(client, model="qwen3.8-max")
    assert r.status_code == 200, r.text
    assert llm_mocks["models"] == ["qwen3.8-max"]  # premium behåller valet


def test_turn_cap_zero_is_unlimited(client):
    """0 = oändligt (samma semantik som före FAS A) — får aldrig ge 403."""
    _register(client)
    _make_campaign("alice")
    _patch_user("alice", turn_cap=0, turn_bonus=0, turns_used=0)
    assert main._turns_available("alice") == 999999
    # även efter många förbrukade turns
    _patch_user("alice", turns_used=999)
    assert main._turns_available("alice") == 999999
    r = _chat(client)
    assert r.status_code == 200, r.text


def test_premium_unlimited(client):
    _register(client)
    _patch_user("alice", subscription_status="premium", subscription_until=_in_days(30),
                turn_cap=1, turns_used=100, turn_bonus=0)
    assert main._tier_for("alice") == "premium"
    assert main._turns_available("alice") == 999999


def test_expired_premium_demoted(client):
    _register(client)
    _patch_user("alice", subscription_status="premium", subscription_until=_in_days(-1),
                turn_cap=5, turns_used=0)
    assert main._tier_for("alice") == "free"
    # demote är sparat i users.json
    assert _user()["subscription_status"] == "free"


# ── Bakåtkompatibilitet ──────────────────────────────────────────────────

def test_legacy_account_backfilled(client):
    """Konto utan FAS A-fält → setdefault fyller i utan krasch."""
    main.save_users({
        "old_timer": {"password_hash": hash_password("secret123"), "role": "player", "turn_cap": 50},
    })
    assert main._turns_available("old_timer") == 50
    u = _user("old_timer")
    assert u["turns_used"] == 0
    assert u["turn_bonus"] == 0
    # Backfill sätter reset_date=today; första kollen rullar direkt till +1
    # (idag >= reset_date) — utan att förlora några turns.
    assert u["reset_date"] == _in_days(1)
    assert u["subscription_status"] == "free"
    assert u["subscription_until"] is None
