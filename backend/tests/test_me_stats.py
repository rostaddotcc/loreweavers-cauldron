"""Spelarprofil — GET /api/me/stats (2026-08-04).

autouse-fixtures: ALLA tester pekar users.json + kampanjer mot tmp —
ALDRIG riktig data.
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
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", email=None):
    u = {"password_hash": hash_password("secret123"), "role": role,
         "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
         "reset_date": "2026-08-04", "subscription_status": "free",
         "subscription_until": None, "created_at": "2026-08-01T10:00:00+00:00",
         "last_login": "2026-08-04T09:00:00+00:00"}
    if email:
        u["email"] = email
    main.save_users({username: u})


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _seed_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def test_me_stats_requires_login(client):
    r = client.get("/api/me/stats")
    assert r.status_code == 401


def test_me_stats_own_profile_no_geo(client):
    _seed("alice", email="alice@example.com")
    _seed_campaign("alice")
    r = client.get("/api/me/stats", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    s = r.json()["stats"]
    assert s["username"] == "alice"
    assert s["role"] == "player"
    assert s["email"] == "alice@example.com"
    assert s["total_campaigns"] == 1
    assert "total_tokens" in s
    assert "turn_cap" in s
    assert "subscription_status" in s
    assert "tts_seconds" in s
    # INGA geo-fält — spelare ser aldrig ip/land
    for banned in ("ip", "country", "country_code", "country_flag"):
        assert banned not in s


def test_me_stats_cannot_read_others(client):
    """Endpointen tar ingen user-param — cookie bestämmer VEM du ser."""
    _seed("alice")
    _seed("bob")
    r = client.get("/api/me/stats", cookies={"morkrets_token": _tok("bob")})
    assert r.status_code == 200
    s = r.json()["stats"]
    assert s["username"] == "bob"
    assert "alice" not in str(s)


def test_me_stats_admin_sees_own(client):
    _seed("the_admin", role="admin")
    r = client.get("/api/me/stats", cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200
    s = r.json()["stats"]
    assert s["username"] == "the_admin"
    assert s["role"] == "admin"
