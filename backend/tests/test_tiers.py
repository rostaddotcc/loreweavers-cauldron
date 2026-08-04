"""TIERS 2026-08: free < tier1 < tier2 < lifetime.

Täcker:
  - avatar-gate: free → 403 på campaign-avatar + vault-avatar; tier1+ OK; admin OK
  - 6-timmars-rollover: tier1/tier2 reset_ts → turns_used nollställs efter 6 h
  - free behåller daglig rollover (reset_date)
  - legacy "premium" i users.json → tier2

Ingen riktig data rörs: users.json + kampanj-data pekas om till tmp
(autouse-fixtures — users.json-incidenten 2026-08-04).
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
    monkeypatch.setattr(sm, "VAULTS_DIR", tmp_path / "vaults")
    return d


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(username="alice", role="player", tier="free", until=None, turn_cap=50):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": role,
                   "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": _in_days(0),
                   "subscription_status": tier,
                   "subscription_until": until},
    })


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _seed_campaign(username, cid="c1"):
    """Skapa en kampanj så campaign-avatar-endpointen har state."""
    main.store.create(username, name="Test Campaign", language="en")


class _FakeResp:
    status_code = 200

    def json(self):
        return {"data": [{"b64_json": "QUJD"}]}


class _FakePost:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _FakeResp()


def test_legacy_premium_maps_to_tier2():
    _seed("alice", tier="premium", until=_in_days(30))
    assert main._tier_for("alice") == "tier2"
    assert main._period_hours_for(main._tier_for("alice")) == 6


def test_tier1_period_is_6h():
    assert main._period_hours_for("free") == 24
    assert main._period_hours_for("tier1") == 6
    assert main._period_hours_for("tier2") == 6
    assert main._period_hours_for("lifetime") == 0


def test_six_hour_rollover(client):
    """tier1: reset_ts passerad → turns_used nollställs, ny reset +6 h."""
    _seed("alice", tier="tier1", until=_in_days(30))
    users = main.load_users()
    users["alice"]["turns_used"] = 40
    users["alice"]["reset_ts"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    main.save_users(users)
    assert main._turns_available("alice") == 50  # nollställd
    u = main.load_users()["alice"]
    assert u["turns_used"] == 0
    new_ts = datetime.fromisoformat(u["reset_ts"])
    assert new_ts > datetime.now(timezone.utc)  # framflyttad +6 h


def test_six_hour_rollover_not_due(client):
    """tier1: reset_ts i framtiden → inga nollställningar."""
    _seed("alice", tier="tier1", until=_in_days(30))
    users = main.load_users()
    users["alice"]["turns_used"] = 40
    users["alice"]["reset_ts"] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    main.save_users(users)
    assert main._turns_available("alice") == 10  # 50 - 40


def test_free_still_daily_rollover(client):
    """free behåller daglig (reset_date) — inga reset_ts-fält."""
    _seed("alice")
    main.load_users()["alice"]["turns_used"] = 40
    main.load_users()["alice"]["reset_date"] = _in_days(-1)
    main.save_users(main.load_users())
    assert main._turns_available("alice") == 50


def test_lifetime_never_rolls_over(client):
    _seed("alice", tier="lifetime", until=_in_days(3650), turn_cap=0)
    main.load_users()["alice"]["turns_used"] = 999
    main.save_users(main.load_users())
    assert main._turns_available("alice") == 999999


# ── Avatar-gate ──────────────────────────────────────────────────────────

def test_campaign_avatar_gate_free_403(client, monkeypatch):
    _seed("alice")
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar/generate", json={"kind": "player"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Tier 1" in r.json()["detail"]


def test_campaign_avatar_gate_tier1_ok(client, monkeypatch):
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice", tier="tier1", until=_in_days(30))
    _seed_campaign("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/campaign/avatar/generate", json={"kind": "player", "prompt": "a hero"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


def test_campaign_avatar_gate_admin_ok(client, monkeypatch):
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("the_admin", role="admin")
    _seed_campaign("the_admin")
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/campaign/avatar/generate", json={"kind": "player", "prompt": "a hero"},
                    cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200, r.text


# ── Avatar-UPPladdning är också tier1+ (2026-08-04) ────────────────────

def test_campaign_avatar_upload_gate_free_403(client, monkeypatch):
    """Upload-avataren ligger bakom paywall — free → 403."""
    _seed("alice")
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar",
                    data={"kind": "player"},
                    files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Tier 1" in r.json()["detail"]


def test_campaign_avatar_upload_gate_tier1_ok(client, monkeypatch):
    """tier1 får ladda upp (samma gate som AI-generering)."""
    _seed("alice", tier="tier1", until=_in_days(30))
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar",
                    data={"kind": "player"},
                    files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_vault_avatar_gate_free_403(client, monkeypatch):
    _seed("alice")
    # Skapa en valv-karaktär
    vault = sm.CharacterVault()
    entry = vault.save("alice", {"name": "Al", "race": "Human", "class": "Fighter", "level": 1})
    monkeypatch.setattr(main, "vault", vault)
    r = client.post(f"/api/vault/characters/{entry['id']}/avatar/generate", json={},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Tier 1" in r.json()["detail"]


# ── Riktig lifetime (∞) + chattlogg vid grant ──────────────────────────

def test_lifetime_without_until_never_expires():
    """lifetime med until=None får ALDRIG demotas till free (2026-08-04)."""
    _seed("alice", tier="lifetime", until=None, turn_cap=0)
    assert main._tier_for("alice") == "lifetime"
    assert main._turns_available("alice") == 999999


def test_lifetime_old_until_date_still_valid():
    """lifetime med passerat until-datum (legacy +3650-dagar) upphör inte."""
    _seed("alice", tier="lifetime", until=_in_days(-1), turn_cap=0)
    assert main._tier_for("alice") == "lifetime"


def test_admin_subscription_lifetime_forces_until_null(client):
    """Admin-grant av lifetime → until=null (oändlig), turn_cap 0."""
    _seed("the_admin", role="admin")
    _seed("alice")
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "lifetime", "until": "2027-01-01"},
                   cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200
    data = r.json()
    assert data["subscription_status"] == "lifetime"
    assert data["subscription_until"] is None
    assert data["turn_cap"] == 0
    assert main._tier_for("alice") == "lifetime"


def test_admin_subscription_appends_chat_log(client):
    """Grant skriver en loggpost i spelarens aktiva kampanjtranskript."""
    _seed("the_admin", role="admin")
    _seed("alice")
    _seed_campaign("alice")
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "tier2", "until": _in_days(30)},
                   cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200
    state = main.store.get("alice")
    assert state is not None
    trans = main.store.load_transcript(state, last_n=10)
    assert any("upgraded as a token of appreciation" in e["content"] for e in trans)
    assert any("Tier 2" in e["content"] for e in trans)


def test_admin_subscription_lifetime_log_says_lifetime(client):
    _seed("the_admin", role="admin")
    _seed("alice")
    _seed_campaign("alice")
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "lifetime"},
                   cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200
    state = main.store.get("alice")
    trans = main.store.load_transcript(state, last_n=10)
    assert any("Lifetime" in e["content"] and "∞" in e["content"] for e in trans)


def test_admin_subscription_free_log(client):
    """Återkallning till free skriver en informativ loggpost."""
    _seed("the_admin", role="admin")
    _seed("alice", tier="tier2", until=_in_days(30))
    _seed_campaign("alice")
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "free"},
                   cookies={"morkrets_token": _tok("the_admin", "admin")})
    assert r.status_code == 200
    state = main.store.get("alice")
    trans = main.store.load_transcript(state, last_n=10)
    assert any("reverted to" in e["content"] for e in trans)
