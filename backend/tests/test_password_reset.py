"""Lösenordsåterställning — /api/auth/reset-password (2026-08-04).

autouse-fixtures: ALLA tester pekar users.json mot tmp — ALDRIG riktig data.
"""
import sys
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


def _seed(username="alice", password="secret123"):
    main.save_users({
        username: {"password_hash": hash_password(password), "role": "player",
                   "turn_cap": 50, "turns_used": 3, "turn_bonus": 0,
                   "reset_date": "2026-08-04", "subscription_status": "free",
                   "subscription_until": None},
    })


def test_reset_password_changes_hash_and_logs_in(client):
    _seed("alice", "oldpass123")
    # Gammalt lösenord funkar först
    r = client.post("/api/login", json={"username": "alice", "password": "oldpass123"})
    assert r.status_code == 200

    # Återställ
    r = client.post("/api/auth/reset-password",
                    json={"username": "alice", "password": "newpass456"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Nya lösenordet funkar
    r = client.post("/api/login", json={"username": "alice", "password": "newpass456"})
    assert r.status_code == 200
    # Gamla funkar inte längre
    r = client.post("/api/login", json={"username": "alice", "password": "oldpass123"})
    assert r.status_code == 401


def test_reset_password_unknown_user_404(client):
    r = client.post("/api/auth/reset-password",
                    json={"username": "ghost", "password": "whatever123"})
    assert r.status_code == 404


def test_reset_password_invalid_password_400(client):
    _seed("alice", "oldpass123")
    r = client.post("/api/auth/reset-password",
                    json={"username": "alice", "password": "x"})
    assert r.status_code == 400


def test_reset_password_sets_session_cookie(client):
    _seed("alice", "oldpass123")
    r = client.post("/api/auth/reset-password",
                    json={"username": "alice", "password": "freshpass1"})
    assert r.status_code == 200
    assert "morkrets_token" in r.headers.get("set-cookie", "")
