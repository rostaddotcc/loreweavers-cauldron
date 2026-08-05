"""TIERS 2026-08-05: one-time-förmåner — free < tier1 (Support 3€) < tier2 (Patron 10€) < lifetime.

Täcker:
  - avatar-generering (StepFun): GRATIS för alla tier; upload tier1+
  - Wan 2.7: Patron+ (10€) — free/tier1 → 403
  - alla (utom lifetime) får 50 turns/dag (24h-period)
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


def _seed(username="alice", role="player", tier="free", until=None, turn_cap=50, features=None, models_until=None):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": role,
                   "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": _in_days(0),
                   "subscription_status": tier,
                   "subscription_until": until,
                   "features": features or {},
                   "models_until": models_until,
                   "start_bonus_granted": True,
                   "wan_used_today": 0, "wan_reset_date": _in_days(0)},
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


# Wan 2.7-svar (DashScope-shape) + nerladdning av bild-URL:en
class _WanResp:
    status_code = 200

    def json(self):
        return {"output": {"choices": [{"message": {"content": [{"type": "image", "image": "http://fake.example/avatar.png"}]}}]}}

    def raise_for_status(self):
        return None


class _WanClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _WanResp()

    async def get(self, url, **k):
        class _DL:
            status_code = 200
            content = b"fake-png-bytes"

            def raise_for_status(self):
                pass

        return _DL()


def test_legacy_premium_maps_to_tier2():
    _seed("alice", tier="premium", until=_in_days(30))
    assert main._tier_for("alice") == "tier2"
    assert main._period_hours_for(main._tier_for("alice")) == 24  # alla får 50/dag


def test_period_hours_all_24_except_lifetime():
    assert main._period_hours_for("free") == 24
    assert main._period_hours_for("tier1") == 24
    assert main._period_hours_for("tier2") == 24
    assert main._period_hours_for("lifetime") == 0


def test_daily_rollover_applies_to_all_tiers(client):
    """one-time-modellen: ALLA (utom lifetime) rullar dagligen — ingen 6h-period."""
    for tier in ("free", "tier1", "tier2"):
        _seed("alice", tier=tier, until=_in_days(30) if tier != "free" else None,
              features=({"export": True, "all_models": True, "wan1080": True} if tier == "tier2" else ({"export": True} if tier == "tier1" else None)),
              models_until=_in_days(30) if tier == "tier2" else None)
        users = main.load_users()
        users["alice"]["turns_used"] = 40
        users["alice"]["reset_date"] = _in_days(-1)
        main.save_users(users)
        assert main._turns_available("alice") == 50  # nollställd dagligen


def test_lifetime_never_rolls_over(client):
    _seed("alice", tier="lifetime", until=_in_days(3650), turn_cap=0)
    main.load_users()["alice"]["turns_used"] = 999
    main.save_users(main.load_users())
    assert main._turns_available("alice") == 999999


# ── Avatar-generering är GRATIS för alla tier (2026-08-05) ──────────────
# "Paint new from my words" är fritt — haken för att locka fler karaktärer.
# Upload förblir tier1+ (Support).

def test_campaign_avatar_generate_free_ok(client, monkeypatch):
    """Free-tier får AI-generera avatar (friprompt) — ingen paywall."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice")
    _seed_campaign("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/campaign/avatar/generate", json={"kind": "player", "prompt": "a hooded hero"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


# ── Wan 2.7 = Patron+ (10€, premium-bildmotor) ──────────────────────────

def test_campaign_avatar_wan_gate_free_403(client):
    """Free-tier: Wan 2.7 är låst — 403 med uppgraderingshänvisning."""
    _seed("alice")
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar/generate",
                    json={"kind": "player", "prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]


def test_campaign_avatar_wan_gate_tier1_403(client):
    """Support (tier1, 3€): Wan fortfarande låst."""
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar/generate",
                    json={"kind": "player", "prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403


def test_campaign_avatar_wan_tier2_ok(client, monkeypatch):
    """Patron (tier2, 10€): Wan 2.7 målar — 200."""
    _seed("alice", tier="tier2", until=_in_days(30), features={"export": True, "wan1080": True, "all_models": True}, models_until=_in_days(30))
    _seed_campaign("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _WanClient)
    r = client.post("/api/campaign/avatar/generate",
                    json={"kind": "player", "prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


def test_campaign_avatar_wan_respects_daily_quota(client, monkeypatch):
    """Patron: max 10 Wan-bilder/dag → 11:e ger 403."""
    _seed("alice", tier="tier2", until=_in_days(30), features={"export": True, "wan1080": True, "all_models": True}, models_until=_in_days(30))
    _seed_campaign("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _WanClient)
    users = main.load_users()
    users["alice"]["wan_used_today"] = main.WAN_DAILY_LIMIT
    main.save_users(users)
    r = client.post("/api/campaign/avatar/generate",
                    json={"kind": "player", "prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "daily limit" in r.json()["detail"]


def test_campaign_avatar_gate_tier1_ok(client, monkeypatch):
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
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


# ── Avatar-UPPladdning är tier1+ (Support 3€) ──────────────────────────

def test_campaign_avatar_upload_gate_free_403(client, monkeypatch):
    """Upload-avataren ligger bakom paywall — free → 403."""
    _seed("alice")
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar",
                    data={"kind": "player"},
                    files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Support" in r.json()["detail"]


def test_campaign_avatar_upload_gate_tier1_ok(client, monkeypatch):
    """Support (3€) får ladda upp."""
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
    _seed_campaign("alice")
    r = client.post("/api/campaign/avatar",
                    data={"kind": "player"},
                    files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_vault_avatar_generate_free_ok(client, monkeypatch):
    """Valvet: StepFun-generering är GRATIS för free (2026-08-05)."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice")
    vault = sm.CharacterVault()
    entry = vault.save("alice", {"name": "Al", "race": "Human", "class": "Fighter", "level": 1})
    monkeypatch.setattr(main, "vault", vault)
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post(f"/api/vault/characters/{entry['id']}/avatar/generate", json={},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


def test_vault_avatar_wan_gate_free_403(client, monkeypatch):
    """Valvet: Wan 2.7 låst för free — 403 med Patron-hänvisning."""
    _seed("alice")
    vault = sm.CharacterVault()
    entry = vault.save("alice", {"name": "Al", "race": "Human", "class": "Fighter", "level": 1})
    monkeypatch.setattr(main, "vault", vault)
    r = client.post(f"/api/vault/characters/{entry['id']}/avatar/generate",
                    json={"prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]


def test_vault_avatar_wan_gate_tier1_403(client, monkeypatch):
    """Valvet: Support (tier1) får Patron-hänvisning för Wan."""
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
    vault = sm.CharacterVault()
    entry = vault.save("alice", {"name": "Al", "race": "Human", "class": "Fighter", "level": 1})
    monkeypatch.setattr(main, "vault", vault)
    r = client.post(f"/api/vault/characters/{entry['id']}/avatar/generate",
                    json={"prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]


def test_vault_avatar_wan_tier2_ok(client, monkeypatch):
    """Patron (tier2): Wan målar även i valvet — 200."""
    _seed("alice", tier="tier2", until=_in_days(30), features={"export": True, "wan1080": True, "all_models": True}, models_until=_in_days(30))
    vault = sm.CharacterVault()
    entry = vault.save("alice", {"name": "Al", "race": "Human", "class": "Fighter", "level": 1})
    monkeypatch.setattr(main, "vault", vault)
    monkeypatch.setattr(main.httpx, "AsyncClient", _WanClient)
    r = client.post(f"/api/vault/characters/{entry['id']}/avatar/generate",
                    json={"prompt": "a hero", "provider": "wan"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


# ── Export / Forge-gating (3€ Support) ──────────────────────────────────

def test_campaign_export_free_403(client):
    _seed("alice")
    _seed_campaign("alice")
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Support" in r.json()["detail"]


def test_campaign_export_support_ok(client):
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
    _seed_campaign("alice")
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text


def test_vault_export_free_403(client):
    _seed("alice")
    r = client.get("/api/vault/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
    assert "Support" in r.json()["detail"]


def test_vault_export_support_ok(client):
    _seed("alice", tier="tier1", until=_in_days(30), features={"export": True})
    r = client.get("/api/vault/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    assert "characters" in r.json()


# ── Spelarprofilens avatar (konto — StepFun, gratis, SEPARAT) ───────────

def test_me_avatar_generate_free_ok(client, monkeypatch):
    """Free-tier målar sin PROFILavatar med StepFun — alltid gratis."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/me/avatar/generate", json={"prompt": "a hooded mage"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    assert main._user_avatar_path("alice").exists()
    me = client.get("/api/me", cookies={"morkrets_token": _tok()}).json()
    assert me["has_avatar"] is True
    av = client.get("/api/me/avatar", cookies={"morkrets_token": _tok()})
    assert av.status_code == 200


def test_me_avatar_delete(client, monkeypatch):
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice")
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    client.post("/api/me/avatar/generate", json={}, cookies={"morkrets_token": _tok()})
    r = client.delete("/api/me/avatar", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert not main._user_avatar_path("alice").exists()
    me = client.get("/api/me", cookies={"morkrets_token": _tok()}).json()
    assert me["has_avatar"] is False


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
