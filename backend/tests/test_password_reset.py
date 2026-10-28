"""Lösenordsåterställning — /api/auth/reset-password (2026-08-04).

autouse-fixtures: ALLA tester pekar users.json mot tmp — ALDRIG riktig data.
"""
import json
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
    # Direkt-flödets rate limit (in-memory) får inte läcka mellan tester.
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


@pytest.fixture(autouse=True)
def outbox_dir(tmp_path, monkeypatch):
    """Peka OUTBOX_DIR mot tmp — autouse så inget test skriver riktiga mail."""
    d = tmp_path / "outbox"
    monkeypatch.setattr(main, "OUTBOX_DIR", d)
    return d


def _seed(username="alice", password="secret123", email=None):
    u = {"password_hash": hash_password(password), "role": "player",
         "turn_cap": 50, "turns_used": 3, "turn_bonus": 0,
         "reset_date": "2026-08-04", "subscription_status": "free",
         "subscription_until": None}
    if email:
        u["email"] = email
    main.save_users({username: u})


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


# ── Härdning 2026-08-04 (security audit P0) ────────────────────────────

def test_reset_password_admin_blocked(client):
    u = {"password_hash": hash_password("adminpw123"), "role": "admin",
         "turn_cap": 0, "turns_used": 0, "turn_bonus": 0,
         "reset_date": "2026-08-04", "subscription_status": "free",
         "subscription_until": None}
    main.save_users({"admin": u})
    r = client.post("/api/auth/reset-password",
                    json={"username": "admin", "password": "HACKED123"})
    assert r.status_code == 403
    # Lösenordet får INTE ha ändrats
    assert auth.verify_password("adminpw123", main.load_users()["admin"]["password_hash"])


def test_reset_password_email_account_blocked(client):
    _seed("alice", "oldpass123", email="alice@example.com")
    r = client.post("/api/auth/reset-password",
                    json={"username": "alice", "password": "HACKED123"})
    assert r.status_code == 403
    assert auth.verify_password("oldpass123", main.load_users()["alice"]["password_hash"])


def test_reset_password_rate_limited(client):
    _seed("alice", "oldpass123")
    r1 = client.post("/api/auth/reset-password",
                     json={"username": "alice", "password": "newpass456"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/reset-password",
                     json={"username": "alice", "password": "newpass789"})
    assert r2.status_code == 429


# ── E-postbaserad reset (request-reset + reset-with-token) ─────────────

def test_request_reset_with_email_writes_outbox(client, outbox_dir):
    _seed("alice", email="alice@example.com")
    r = client.post("/api/auth/request-reset", json={"username": "alice"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    files = list(outbox_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["to"] == "alice@example.com"
    assert "dnd.rostad.cc/reset.html?token=" in payload["body"]
    # Token sparad i users.json
    u = main.load_users()["alice"]
    assert u["reset_token"]
    assert u["reset_token_expiry"]


def test_request_reset_without_email_no_outbox(client, outbox_dir):
    _seed("alice")  # ingen e-post
    r = client.post("/api/auth/request-reset", json={"username": "alice"})
    assert r.status_code == 200
    assert list(outbox_dir.glob("*.json")) == []
    assert "reset_token" not in main.load_users()["alice"]


def test_request_reset_unknown_user_no_enumeration(client, outbox_dir):
    """Okänd användare får samma svar — inga konton avslöjas."""
    r = client.post("/api/auth/request-reset", json={"username": "ghost"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert list(outbox_dir.glob("*.json")) == []


def test_request_reset_rate_limited(client, outbox_dir):
    _seed("alice", email="alice@example.com")
    r1 = client.post("/api/auth/request-reset", json={"username": "alice"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/request-reset", json={"username": "alice"})
    assert r2.status_code == 429


def test_reset_with_token_changes_password_and_logs_in(client, outbox_dir):
    _seed("alice", "oldpass123", email="alice@example.com")
    client.post("/api/auth/request-reset", json={"username": "alice"})
    token = main.load_users()["alice"]["reset_token"]
    r = client.post("/api/auth/reset-with-token",
                    json={"token": token, "password": "brandnew1"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "alice"
    assert "morkrets_token" in r.headers.get("set-cookie", "")
    # Token borttagen (one-time-use) + nytt lösenord fungerar
    u = main.load_users()["alice"]
    assert "reset_token" not in u
    assert auth.verify_password("brandnew1", u["password_hash"])
    assert not auth.verify_password("oldpass123", u["password_hash"])


def test_reset_with_token_one_time_use(client, outbox_dir):
    _seed("alice", "oldpass123", email="alice@example.com")
    client.post("/api/auth/request-reset", json={"username": "alice"})
    token = main.load_users()["alice"]["reset_token"]
    r1 = client.post("/api/auth/reset-with-token",
                     json={"token": token, "password": "brandnew1"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/reset-with-token",
                     json={"token": token, "password": "brandnew2"})
    assert r2.status_code == 400
    assert "invalid or already used" in r2.json()["detail"]


def test_reset_with_token_expired(client, outbox_dir):
    from datetime import datetime, timedelta, timezone
    _seed("alice", "oldpass123", email="alice@example.com")
    client.post("/api/auth/request-reset", json={"username": "alice"})
    u = main.load_users()
    u["alice"]["reset_token_expiry"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    main.save_users(u)
    token = u["alice"]["reset_token"]
    r = client.post("/api/auth/reset-with-token",
                    json={"token": token, "password": "brandnew1"})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"]


def test_reset_with_token_invalid(client):
    r = client.post("/api/auth/reset-with-token",
                    json={"token": "nope", "password": "brandnew1"})
    assert r.status_code == 400


def test_reset_with_token_invalid_password(client, outbox_dir):
    _seed("alice", "oldpass123", email="alice@example.com")
    client.post("/api/auth/request-reset", json={"username": "alice"})
    token = main.load_users()["alice"]["reset_token"]
    r = client.post("/api/auth/reset-with-token",
                    json={"token": token, "password": "x"})
    assert r.status_code == 400
