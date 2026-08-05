"""2026-08-05 v2: 30-dagars förmånsfönster + stackning + provider-stats.

Rostads pricing-rebuild:
  - 3€/10€ = en MÅNAD förmåner (features_until), stackbart
  - köpta turns BEHÅLLS efter att fönstret löpt ut (turn_bonus)
  - Patron-paketet inkluderar Qwen TTS (tier2-gaten → fönstret)
  - admin-stats: token share + totala anrop per provider
  - self-service kontoradering (DELETE /api/me/account)
  - export inkluderar alla bilder (kampanj-avatars + forge-zip)
"""

import sys
import json
import zipfile
import io
from datetime import datetime, timedelta, timezone
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
    monkeypatch.setattr(sm, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(main, "VAULTS_DIR", tmp_path / "vaults")
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture(autouse=True)
def stripe_env(monkeypatch):
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", "whsec_test123")
    monkeypatch.setattr(main, "STRIPE_PRICES", {
        "support300": "price_sup300", "patron500": "price_pat500",
        "donation": "", "lifetime": "price_lt",
    })


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, stripe_env):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", tier="free", features=None, turn_bonus=0):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": role,
                   "turn_cap": 50, "turns_used": 0, "turn_bonus": turn_bonus,
                   "reset_date": "2026-08-04", "subscription_status": tier,
                   "subscription_until": None,
                   "features": features or {},
                   "start_bonus_granted": True,
                   "email": "alice@example.com"},
    })


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _sign(payload: bytes) -> str:
    import hashlib
    import hmac
    import time
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_test123", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event(etype, obj, event_id="evt_stack"):
    return json.dumps({"id": event_id, "type": etype, "data": {"object": obj}}).encode()


def _in_days(n):
    return (datetime.now(timezone.utc).date() + timedelta(days=n)).isoformat()


def _webhook(client, tier, username="alice", event_id="evt_x"):
    body = _event("checkout.session.completed", {
        "metadata": {"username": username, "tier": tier},
        "client_reference_id": username,
        "payment_status": "paid",
        "amount_total": 1000,
    }, event_id=event_id)
    return client.post("/api/stripe/webhook", content=body,
                       headers={"stripe-signature": _sign(body)})


# ── 30-dagarsfönster + stackning ─────────────────────────────────────────

def test_support_gives_30_day_window(client):
    _seed()
    r = _webhook(client, "support300", event_id="evt_s1")
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 300
    assert u["features"]["export"] is True
    assert u["features_until"] == _in_days(30)
    assert main._tier_for("alice") == "tier1"


def test_patron_gives_30_day_window_with_qwen_tts(client):
    _seed()
    r = _webhook(client, "patron500", event_id="evt_p1")
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 500
    assert u["features_until"] == _in_days(30)
    assert main._tier_for("alice") == "tier2"
    # Patron → Qwen TTS tillgängligt (30 dagar)
    assert main._tier_for("alice") in ("tier2", "lifetime")


def test_stack_two_support_packs_extends_window_and_turns(client):
    _seed()
    _webhook(client, "support300", event_id="evt_a")
    _webhook(client, "support300", event_id="evt_b")
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 600  # 300 + 300 (båda behålls)
    assert u["features_until"] == _in_days(60)  # 30 + 30 (staplat)


def test_stack_patron_on_top_of_support(client):
    _seed()
    _webhook(client, "support300", event_id="evt_a")
    _webhook(client, "patron500", event_id="evt_b")
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 800
    assert u["features_until"] == _in_days(60)  # fönstret förlängs från nuvarande
    assert main._tier_for("alice") == "tier2"  # Patron-förmånerna gäller


def test_purchase_after_expiry_starts_fresh_window(client):
    _seed()
    _webhook(client, "support300", event_id="evt_a")
    u = main.load_users()["alice"]
    u["features_until"] = _in_days(-5)  # fönstret gick ut för 5 dagar sedan
    main.save_users({"alice": u})
    assert main._tier_for("alice") == "free"  # inga förmåner kvar
    _webhook(client, "support300", event_id="evt_b")
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 600  # köpta turns BEHÅLLS (300 + 300)
    assert u["features_until"] == _in_days(30)  # nytt fönster från idag


def test_turns_survive_benefits_expiry(client):
    _seed(turn_bonus=300)
    u = main.load_users()["alice"]
    u["features"] = {"export": True, "all_models": True, "wan1080": True}
    u["features_until"] = _in_days(-1)
    main.save_users({"alice": u})
    assert main._tier_for("alice") == "free"  # förmåner löpta
    info = main._user_free_info("alice")
    assert info["turn_bonus"] == 300  # turns kvar på kontot
    assert info["features"]["benefits_active"] is False


def test_legacy_features_without_until_stay_active(client):
    """Admin-grants/gamla konton utan features_until → förmåner permanenta."""
    _seed(features={"export": True})
    assert main._tier_for("alice") == "tier1"
    info = main._user_free_info("alice")
    assert info["features"]["benefits_active"] is True


def test_expired_export_no_longer_exports(client):
    _seed()
    _webhook(client, "support300", event_id="evt_a")
    u = main.load_users()["alice"]
    u["features_until"] = _in_days(-1)
    main.save_users({"alice": u})
    main.store.create("alice", name="T", language="en")
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 403  # förmånen löpt → export borta


# ── Admin-stats: provider-aggregation ────────────────────────────────────

def test_admin_stats_providers_and_models(client):
    _seed()
    main.store.create("alice", name="T", language="en")
    st = main.store.get("alice")
    # Simulera transkript-poster med olika modeller
    tdir = main.store.get_transcripts_dir(st)
    tdir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"role": "assistant", "content": "a", "ts": "2026-08-05T10:00:00",
         "meta": {"model": "qwen3.8-max", "tokens": {"prompt_tokens": 100, "completion_tokens": 50}}},
        {"role": "assistant", "content": "b", "ts": "2026-08-05T10:01:00",
         "meta": {"model": "step-3.7-flash", "tokens": {"prompt_tokens": 30, "completion_tokens": 10}}},
    ]
    with open(tdir / "session-1.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    r = client.get("/api/admin/stats", cookies={"morkrets_token": create_token("admin", "admin")})
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data and "models" in data
    # qwen3.8-max → dashscope; step-3.7-flash → stepfun
    assert data["providers"]["dashscope"]["tokens"] == 150
    assert data["providers"]["stepfun"]["tokens"] == 40
    assert data["providers"]["dashscope"]["calls"] == 1
    assert data["providers"]["stepfun"]["calls"] == 1
    assert data["models"]["qwen3.8-max"]["provider"] == "dashscope"
    # Per-användarraden har model_tokens (för detaljvy) — rå form prompt/completion
    mt = data["users"][0]["model_tokens"]["qwen3.8-max"]
    assert mt["prompt_tokens"] + mt["completion_tokens"] == 150


def test_provider_for_model_fallback(client):
    assert main._provider_for_model("qwen3.8-max") == "dashscope"
    assert main._provider_for_model("deepseek-v4-flash-0731") == "deepseek"
    assert main._provider_for_model("step-3.7-flash") == "stepfun"
    assert main._provider_for_model("mimo-v2.5-pro") == "mimo"
    assert main._provider_for_model("igorls/gemma-4-e4b-it-heretic-GGUF:q4_k_m") == "ollama"
    assert main._provider_for_model("totally-unknown-model") == "unknown"
    assert main._provider_for_model("") == "unknown"


# ── Self-service kontoradering ───────────────────────────────────────────

def test_me_delete_account_removes_everything(client):
    _seed()
    main.store.create("alice", name="T", language="en")
    main.vault.save("alice", {"name": "Hero"}, campaign_name="T", inventory=[])
    # Ledger-rad som ska försvinna
    main._ledger_append({"user": "alice", "amount_sek": 35, "type": "stripe:support300",
                         "event_id": "evt_ledger"})
    # Profilporträtt
    av_dir = Path(main.CAMPAIGNS_DIR).parent / "user_avatars"
    av_dir.mkdir(parents=True, exist_ok=True)
    (av_dir / "alice.png").write_bytes(b"png")

    r = client.delete("/api/me/account", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert r.json()["deleted"] == "alice"
    # users.json: borta
    assert "alice" not in main.load_users()
    # kampanjer borta
    assert not (main.CAMPAIGNS_DIR / "alice").exists()
    # valv borta
    assert not (main.VAULTS_DIR / "alice").exists()
    # profilporträtt borta
    assert not (av_dir / "alice.png").exists()
    # ledger-raderna borta
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert all(e["user"] != "alice" for e in ledger)


def test_me_delete_account_blocks_admin_bootstrap(client):
    main.save_users({
        "admin": {"password_hash": hash_password("x"), "role": "admin",
                  "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                  "features": {}, "start_bonus_granted": True},
    })
    r = client.delete("/api/me/account", cookies={"morkrets_token": create_token("admin", "admin")})
    assert r.status_code == 400
    assert "admin" in main.load_users()


def test_me_delete_account_requires_auth(client):
    r = client.delete("/api/me/account")
    assert r.status_code in (401, 403)


# ── Export: bilder följer med ────────────────────────────────────────────

def test_campaign_export_includes_avatar_images(client):
    _seed(features={"export": True})
    main.store.create("alice", name="T", language="en")
    st = main.store.get("alice")
    cid = st["meta"]["campaign_id"]
    av_dir = main.CAMPAIGNS_DIR / "alice" / cid / "avatars"
    av_dir.mkdir(parents=True, exist_ok=True)
    (av_dir / "player.png").write_bytes(b"\x89PNG fake player")
    (av_dir / "dm.png").write_bytes(b"\x89PNG fake dm")
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "bilagor/avatars/player.png" in names
    assert "bilagor/avatars/dm.png" in names
    assert zf.read("bilagor/avatars/player.png") == b"\x89PNG fake player"


def test_vault_export_includes_avatar_images(client):
    _seed(features={"export": True})
    entry = main.vault.save("alice", {"name": "Hero"}, campaign_name="T", inventory=[])
    av = {"disk_name": f"vault_{entry['id']}.png"}
    entry["avatar"] = av
    main.vault.update("alice", entry)
    av_dir = main.vault.avatars_dir("alice")
    av_dir.mkdir(parents=True, exist_ok=True)
    (av_dir / av["disk_name"]).write_bytes(b"\x89PNG forge hero")
    r = client.get("/api/vault/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "forge-export.json" in names
    assert f"avatars/{av['disk_name']}" in names
    assert zf.read(f"avatars/{av['disk_name']}") == b"\x89PNG forge hero"
