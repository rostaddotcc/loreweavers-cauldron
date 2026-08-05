"""TIERS 2026-08-05: TTS + profilavatar är tier-gated.

- StepFun TTS = Support (3€)+ — free → 403 (förr "always free").
- Qwen TTS = Patron (10€)+ — free/tier1 → 403 (förr tyst fallback till stepfun).
- /api/me/avatar/generate: provider 'stepfun'|'wan' (default stepfun).
  StepFun = Support (3€)+; Wan 2.7 = Patron (10€)+. Svaret bär provider.

autouse-fixtures: users.json + kampanjdata pekas mot tmp — skyddar riktig data
(users.json-incidenten 2026-08-04). Ingen riktig data rörs.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import hash_password  # noqa: E402


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


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(username="alice", tier="free", turn_cap=50):
    """free | tier1 (features.export) | tier2 (features.all_models) | lifetime."""
    features = {}
    if tier == "tier1":
        features = {"export": True}
    elif tier == "tier2":
        features = {"export": True, "all_models": True, "wan1080": True}
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": "player",
                   "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": _in_days(0),
                   "subscription_status": tier,
                   "subscription_until": _in_days(30) if tier != "free" else None,
                   "features": features,
                   "models_until": _in_days(30) if tier == "tier2" else None,
                   "start_bonus_granted": True,
                   "wan_used_today": 0, "wan_reset_date": _in_days(0)},
    })


def _login(client, username="alice"):
    r = client.post("/api/login", json={"username": username, "password": "secret123"})
    assert r.status_code == 200
    return r


# ── httpx-mockar (samma mönster som test_tiers.py) ────────────────────────

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


# ── /api/tts: StepFun = Support (3€)+, Qwen = Patron (10€)+ ───────────────

def test_tts_stepfun_free_403(client, monkeypatch):
    """free + stepfun → 403 med Support-hänvisning (förr alltid gratis)."""
    _seed("alice", tier="free")
    _login(client)
    monkeypatch.setattr(main, "_synth_stepfun_tts", lambda voice, text, style="": b"RIFFwavfake")
    r = client.post("/api/tts", json={"text": "Hej från free", "voice": "male", "provider": "stepfun"})
    assert r.status_code == 403
    assert "StepFun TTS is a Support feature (3€)" in r.json()["detail"]


def test_tts_qwen_free_403(client, monkeypatch):
    """free + qwen → 403 (Patron-feature), ingen tyst fallback till stepfun."""
    _seed("alice", tier="free")
    _login(client)
    monkeypatch.setattr(main, "_synth_stepfun_tts", lambda voice, text, style="": b"RIFFwavfake")
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", lambda voice, text, style="": b"RIFFqwenfake")
    r = client.post("/api/tts", json={"text": "Hej qwen free", "voice": "male", "provider": "qwen"})
    assert r.status_code == 403
    assert "Qwen TTS is a Patron feature (10€)" in r.json()["detail"]


def test_tts_stepfun_tier1_ok(client, monkeypatch):
    """Support (tier1) + stepfun → 200."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_synth_stepfun_tts", lambda voice, text, style="": b"RIFFwavfake")
    r = client.post("/api/tts", json={"text": "Hej från support", "voice": "male", "provider": "stepfun"})
    assert r.status_code == 200, r.text
    assert r.content == b"RIFFwavfake"


def test_tts_qwen_tier1_403(client, monkeypatch):
    """Support (tier1) räcker INTE för qwen — 403 med Patron-hänvisning."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", lambda voice, text, style="": b"RIFFqwenfake")
    r = client.post("/api/tts", json={"text": "Hej qwen tier1", "voice": "male", "provider": "qwen"})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]


def test_tts_qwen_tier2_ok(client, monkeypatch):
    """Patron (tier2) + qwen → 200 (premium-röst)."""
    _seed("alice", tier="tier2")
    _login(client)
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", lambda voice, text, style="": b"RIFFqwenfake")
    r = client.post("/api/tts", json={"text": "Hej från patron", "voice": "male", "provider": "qwen"})
    assert r.status_code == 200, r.text
    assert r.content == b"RIFFqwenfake"


# ── /api/me/avatar/generate: provider stepfun|wan ─────────────────────────

def test_me_avatar_stepfun_free_403(client, monkeypatch):
    """free får INTE måla profilavataren med StepFun — 403 + Support."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice", tier="free")
    _login(client)
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/me/avatar/generate", json={"prompt": "a hooded mage", "provider": "stepfun"})
    assert r.status_code == 403
    assert "Support" in r.json()["detail"]


def test_me_avatar_stepfun_tier1_ok(client, monkeypatch):
    """Support (tier1) målar profilavataren med StepFun → 200 + provider."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/me/avatar/generate", json={"prompt": "a hooded mage", "provider": "stepfun"})
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "stepfun"
    assert main._user_avatar_path("alice").exists()


def test_me_avatar_wan_tier1_403(client, monkeypatch):
    """Support (tier1) räcker INTE för Wan 2.7 — 403 med Patron-hänvisning."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", _WanClient)
    r = client.post("/api/me/avatar/generate", json={"prompt": "a hero", "provider": "wan"})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]


def test_me_avatar_wan_tier2_ok(client, monkeypatch):
    """Patron (tier2) målar profilavataren med Wan 2.7 Pro → 200 + provider."""
    _seed("alice", tier="tier2")
    _login(client)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    seen = {}

    class _CapturingWan(_WanClient):
        async def post(self, *a, **k):
            seen["json"] = k.get("json")
            return _WanResp()

    monkeypatch.setattr(main.httpx, "AsyncClient", _CapturingWan)
    r = client.post("/api/me/avatar/generate", json={"prompt": "a hero", "provider": "wan"})
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "wan"
    assert main._user_avatar_path("alice").exists()
    # Patron med features.wan1080 → Wan 2.7 Pro 2048² (samma mönster som vault)
    assert seen["json"]["model"] == "wan2.7-image-pro"
    assert seen["json"]["parameters"]["size"] == "2048*2048"


def test_me_avatar_unknown_provider_defaults_stepfun(client, monkeypatch):
    """Okänd provider → stepfun (inte 400), svaret bär provider."""
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakePost)
    r = client.post("/api/me/avatar/generate", json={"prompt": "x", "provider": "flux"})
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "stepfun"
