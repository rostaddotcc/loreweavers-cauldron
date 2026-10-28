"""Self-host build (SELFHOST=1) — the stripped release.

What this suite pins down, end to end through the real app:

  * no billing: /api/billing/* and /api/stripe/webhook answer 404
  * no turn economy: cap 0, availability 999999, the gate never fires,
    every account resolves to "lifetime" and counts as a supporter
  * models: only what the local Ollama server actually has (embedding models
    filtered out), any cloud id is remapped to the local one
  * the parts that need a paid cloud API (TTS, speech-to-text, image
    generation) answer 501 instead of failing on a missing key
  * /api/config is public and tells the frontend which build it is talking to
  * and the hosted build is untouched: same fixtures, SELFHOST unset

Every test points users.json / campaigns / ledgers at tmp_path — no real data.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
import selfhost  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


# ── isolation (same shape as the other suites) ─────────────────────────────

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


@pytest.fixture(autouse=True)
def outbox_dir(tmp_path, monkeypatch):
    d = tmp_path / "outbox"
    monkeypatch.setattr(main, "OUTBOX_DIR", d)
    return d


@pytest.fixture(autouse=True)
def fake_ollama(monkeypatch):
    """A local Ollama with two chat models and one embedding model.

    Discovery is patched at the HTTP boundary (_fetch_tags), so the real
    filtering, sorting and caching in selfhost.py are what the app sees.
    """
    tags = [
        {"name": "qwen3:8b", "details": {"family": "qwen3"}, "capabilities": ["completion"]},
        {"name": "gemma4:e4b", "details": {"family": "gemma4"}, "capabilities": ["completion", "vision"]},
        {"name": "nomic-embed-text:latest", "details": {"family": "nomic-bert"}, "capabilities": ["embedding"]},
    ]
    monkeypatch.setattr(selfhost, "_fetch_tags", lambda timeout=4.0: tags)
    monkeypatch.delenv("SELFHOST_MODEL", raising=False)
    selfhost.invalidate_cache()
    yield
    selfhost.invalidate_cache()


@pytest.fixture
def client(monkeypatch):
    """App running as the self-host build."""
    monkeypatch.setenv("SELFHOST", "1")
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", turn_cap=50):
    main.save_users({
        username: {
            "password_hash": hash_password("secret123"),
            "role": role,
            "turn_cap": turn_cap,
            "turns_used": 0,
            "turn_bonus": 0,
            "reset_date": "2026-10-28",
            "subscription_status": "free",
            "subscription_until": None,
            "features": {},
            "start_bonus_granted": True,
            "email": "alice@example.com",
        },
    })


def _tok(username="alice", role="player"):
    return create_token(username, role)


# ── no turn economy ───────────────────────────────────────────────────────

def test_turn_quota_is_switched_off(client):
    _seed()
    assert main._turn_cap_for("alice") == 0
    assert main._turns_available("alice") == 999999
    main._gate_turn_quota("alice")          # must not raise 403


def test_every_account_is_lifetime_and_a_supporter(client):
    _seed()
    assert main._tier_for("alice") == "lifetime"
    assert main._is_supporter("alice") is True


def test_me_reports_unlimited_turns(client):
    _seed()
    r = client.get("/api/me", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    me = r.json()
    assert me["turn_cap"] == 0
    assert me["turns_available"] == 999999
    assert me["subscription_status"] == "lifetime"
    assert me["features"]["supporter"] is True


# ── no billing ────────────────────────────────────────────────────────────

def test_billing_routes_are_gone(client):
    _seed()
    tok = _tok()
    r = client.post("/api/billing/checkout", json={"tier": "unlock10"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 404
    r = client.post("/api/billing/portal", cookies={"morkrets_token": tok})
    assert r.status_code == 404
    r = client.post("/api/stripe/webhook", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 404


# ── local models only ─────────────────────────────────────────────────────

def test_config_is_public_and_reports_the_build(client):
    r = client.get("/api/config")           # no cookie on purpose
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["selfhost"] is True
    assert cfg["billing"] is False
    assert cfg["tts"] is False
    assert cfg["images"] is False
    assert cfg["unlimited_turns"] is True
    ids = [m["id"] for m in cfg["models"]]
    assert ids == ["ollama:gemma4:e4b", "ollama:qwen3:8b"]
    assert all("embed" not in i for i in ids)
    assert cfg["default_model"] == "ollama:gemma4:e4b"


def test_models_endpoint_lists_only_local_models(client):
    _seed()
    r = client.get("/api/models", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == ["ollama:gemma4:e4b", "ollama:qwen3:8b"]


def test_cloud_model_ids_are_remapped_to_the_local_one(client):
    _seed()
    assert main._clamp_player_model("qwen3.8-flash") == "ollama:gemma4:e4b"
    assert main._clamp_player_model("ollama:qwen3:8b") == "ollama:qwen3:8b"
    assert main._house_guardian_model() == "ollama:gemma4:e4b"
    assert main._house_extraction_model() == "ollama:gemma4:e4b"


def test_ollama_config_needs_no_api_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.lan:11434/")
    cfg = main.get_model("ollama:qwen3:8b")
    assert cfg.provider == "ollama"
    assert cfg.api_key_env == ""
    assert cfg.base_url == "http://ollama.lan:11434/v1"
    assert main.get_api_key(cfg) is None


# ── the parts that need a paid API ────────────────────────────────────────

def test_voice_and_images_answer_501(client):
    assert client.post("/api/tts", json={"text": "hello"}).status_code == 501
    assert client.post("/api/campaign/avatar/generate", json={}).status_code == 501
    assert client.post("/api/me/avatar/generate", json={}).status_code == 501
    r = client.post("/api/voice", files={"file": ("a.wav", b"RIFF0000", "audio/wav")})
    assert r.status_code == 501
    voices = client.get("/api/tts/voices")
    assert voices.status_code in (200, 401)
    if voices.status_code == 200:
        assert voices.json()["providers"] == []


def test_health_reports_the_build(client):
    assert client.get("/api/health").json()["selfhost"] is True


# ── first start on a clean install ────────────────────────────────────────

def test_admin_is_bootstrapped_from_env(monkeypatch):
    monkeypatch.setenv("SELFHOST", "1")
    monkeypatch.setenv("ADMIN_USER", "keeper")
    monkeypatch.setenv("ADMIN_PASSWORD", "longenough")
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        users = auth.load_users()
        assert users["keeper"]["role"] == "admin"
        r = c.post("/api/login", json={"username": "keeper", "password": "longenough"})
        assert r.status_code == 200


def test_admin_bootstrap_never_overwrites_an_existing_account(monkeypatch):
    monkeypatch.setenv("SELFHOST", "1")
    monkeypatch.setenv("ADMIN_USER", "keeper")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-new-password")
    main.save_users({"keeper": {"password_hash": hash_password("original"),
                                "role": "player", "features": {}}})
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        users = auth.load_users()
        assert users["keeper"]["role"] == "player"          # untouched
        from auth import verify_password
        assert verify_password("original", users["keeper"]["password_hash"])
        assert c.post("/api/login",
                      json={"username": "keeper", "password": "original"}).status_code == 200


# ── the hosted build is untouched ─────────────────────────────────────────

def test_hosted_build_keeps_billing_and_the_daily_cap(monkeypatch):
    monkeypatch.delenv("SELFHOST", raising=False)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        cfg = c.get("/api/config").json()
        assert cfg["selfhost"] is False
        assert cfg["billing"] is True
        assert cfg["unlimited_turns"] is False
        _seed()                              # turn_cap 50 from the seed
        assert main._turn_cap_for("alice") == 50
        assert main._is_supporter("alice") is False
        # the route exists again (401 = login required, not 404 = gone)
        assert c.post("/api/billing/checkout", json={"tier": "unlock10"}).status_code == 401


def test_selfhost_flag_accepts_the_usual_truthy_spellings(monkeypatch):
    for value, expected in (("1", True), ("true", True), (" YES ", True), ("on", True),
                            ("0", False), ("", False), ("no", False)):
        monkeypatch.setenv("SELFHOST", value)
        assert selfhost.enabled() is expected, value