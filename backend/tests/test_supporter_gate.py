"""Supporter-grinden (2026-10-01) — undo + kampanj-export bakom donationen.

Beslut (rostad 2026-10-01): en donation på valfritt belopp (1€+) är en egen
"unlock" som PERMANENT låser upp (a) undo-knappen och (b) kampanj-exporten.
`features.supporter` sätts i varje betalväg och läses DIREKT — aldrig via
`_benefits_active`, eftersom den dömer alla features mot EN gemensam
`features_until` och då skulle låsa en betalare så snart ett legacy-fönster
löpt ut.

Täcker:
  - låst undo för gratiskonto: 403 feature_locked="undo", INGEN turn debiterad,
    oförändrad epoch och snapshoten KVAR (undo fungerar direkt efter unlocken)
  - upplåst undo för: donator, unlock10-köpare, lifetime, admin, samt donator
    vars legacy-fönster löpt ut
  - /api/me exponerar features.supporter (frontend läser den)
  - läsfel på kontodata → 503, aldrig tyst 403
  - _is_supporter-enheten (flagga / legacy-nycklar / betald tier)
  - webhook: unlock10 sätter supporter-flaggan (10€-köparen får aldrig låsas ute)

Alla fixtures pekar users.json, kampanjer, turn-ledgers och billing-ledgern mot
tmp — ALDRIG riktig spelardata (samma mönster som tests/test_undo_turn.py).
"""
import sys
from datetime import datetime, timedelta, timezone
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
    """Gör /api/chat körbar utan LLM — annars kan inget snapshot byggas."""
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


@pytest.fixture(autouse=True)
def stripe_env(monkeypatch):
    """Samma Stripe-värden som tests/test_stripe_billing.py — webhooken är
    signaturkontrollerad, så testet måste signera med tests-hemligheten."""
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", "whsec_test123")


@pytest.fixture
def client(users_file, campaigns_dir, turn_ledgers_dir, ledger_file, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── helpers ──────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(username="alice", role="player", features=None, tier="free", until=None,
          turn_cap=50) -> str:
    """Seeda konto DIREKT (registreringen är rate-limitad process-globalt)."""
    users = main.load_users()
    users[username] = {
        "password_hash": hash_password("secret123"), "role": role,
        "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
        "promo_bonus": 0, "reset_date": _today(), "subscription_status": tier,
        "subscription_until": until, "features": features if features is not None else {},
        "start_bonus_granted": True,
    }
    main.save_users(users)
    return create_token(username, role)


def _login(client, username="alice", role="player", **kw) -> str:
    tok = _seed(username, role=role, **kw)
    client.cookies.set("morkrets_token", tok)
    return tok


def _user(username="alice") -> dict:
    return main.load_users().get(username, {})


def _patch_features(username, features):
    users = main.load_users()
    users[username]["features"] = features
    main.save_users(users)


def _make_campaign(username="alice"):
    return main.store.create(username, name="Test Campaign", language="en")


def _chat(client, message="Hej där!"):
    return client.post("/api/chat", json={"message": message, "model_id": "step-3.7-flash"})


def _actions(username="alice"):
    return [e["action"] for e in main._read_turn_ledger(username)]


# ── låst undo: gratiskontot ──────────────────────────────

def test_undo_locked_for_free_account_costs_nothing(client):
    """403 + feature_locked="undo" — och ingen turn, ingen epoch, ingen muterad state."""
    _login(client)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    before = main.store.get("alice")
    turns_before = _user()["turns_used"]
    epoch_before = before["meta"].get("epoch", 0)
    turn_before = before["meta"]["turn_count"]

    r = client.post("/api/campaign/undo")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["feature_locked"] == "undo"

    after = main.store.get("alice")
    assert _user()["turns_used"] == turns_before      # ingen turn debiterad
    assert after["meta"].get("epoch", 0) == epoch_before
    assert after["meta"]["turn_count"] == turn_before
    assert "undo" not in _actions()


def test_locked_undo_keeps_snapshot_and_works_after_unlock(client):
    """Snapshoten får INTE konsumeras av ett låst försök — annars vore undo
    förbrukad i samma stund spelaren betalar."""
    _login(client)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    assert client.post("/api/campaign/undo").status_code == 403

    _patch_features("alice", {"supporter": True})   # donationen landar
    r = client.post("/api/campaign/undo")
    assert r.status_code == 200, r.text
    assert r.json()["turn_count"] == 0
    assert main.store.get("alice")["meta"]["turn_count"] == 0
    assert _actions() == ["dm", "undo"]


# ── upplåst undo: alla som betalat ───────────────────────

@pytest.mark.parametrize("kwargs,label", [
    ({"features": {"supporter": True}}, "donation"),
    ({"features": {"unlock10": True, "all_models": True, "export": True, "wan1080": True}}, "unlock10"),
    ({"tier": "lifetime", "turn_cap": 0}, "lifetime"),
    ({"role": "admin"}, "admin"),
])
def test_undo_allowed_for_payers(client, kwargs, label):
    _login(client, **kwargs)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    r = client.post("/api/campaign/undo")
    assert r.status_code == 200, f"{label}: {r.text}"
    assert _actions() == ["dm", "undo"]


def test_donor_with_expired_legacy_window_still_undoes(client):
    """Ett utgånget features_until (legacy-köp) får ALDRIG låsa en betalare."""
    _login(client, features={"supporter": True})
    users = main.load_users()
    users["alice"]["features_until"] = _in_days(-1)
    main.save_users(users)
    _make_campaign("alice")
    assert _chat(client).status_code == 200
    assert client.post("/api/campaign/undo").status_code == 200


def test_undo_locked_but_is_supporter_false_for_turn_bonus_without_payment(client):
    """Köpta TURNS utan betalningsväg (admin-topup) är inte ett köp: kontot ska
    inte råka bli supporter av turn_bonus."""
    _login(client)
    users = main.load_users()
    users["alice"]["turn_bonus"] = 500     # topup-grant, ingen betalning
    main.save_users(users)
    assert main._is_supporter("alice") is False


# ── kontraktet ut mot frontend ───────────────────────────

def test_me_exposes_supporter_flag(client):
    _login(client, features={"supporter": True})
    me = client.get("/api/me").json()
    assert me["features"]["supporter"] is True

    client.cookies.clear()
    _login(client, username="bob")
    me = client.get("/api/me").json()
    assert me["features"]["supporter"] is False


def test_gate_returns_503_when_account_cannot_be_read(client, monkeypatch):
    """Läsfel → 503 med ärligt meddelande. En betalare ska aldrig se 'låst'
    för att en transient fel läste fel."""
    _login(client)
    _make_campaign("alice")

    def boom(*a, **k):
        raise OSError("users.json är otillgänglig")

    monkeypatch.setattr(main, "load_users", boom)
    r = client.post("/api/campaign/undo")
    assert r.status_code == 503, r.text
    assert "try again" in r.json()["detail"]["message"].lower()


# ── enheten + grant-vägarna ──────────────────────────────

def test_is_supporter_reads_flag_legacy_keys_and_paid_tiers(client):
    _seed("donator", features={"supporter": True})
    _seed("legacy", features={"export": True})
    _seed("patron", features={"all_models": True})
    _seed("lifetime", tier="lifetime", turn_cap=0)
    _seed("gratis", features={})
    _seed("grants", features={"none": True})

    assert main._is_supporter("donator") is True
    assert main._is_supporter("legacy") is True
    assert main._is_supporter("patron") is True
    assert main._is_supporter("lifetime") is True
    assert main._is_supporter("gratis") is False
    assert main._is_supporter("grants") is False
    assert main._is_supporter("saknas-helt") is False   # okänt konto kraschar inte


def test_unlock10_webhook_sets_supporter_flag(client):
    """10€-köparen betalar 10× en donator — får aldrig låsas ute ur undo/export."""
    _seed("alice")
    body = _stripe_event("unlock10", amount_total=1000)
    r = client.post("/api/stripe/webhook", content=body, headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200, r.text
    assert _user()["features"]["supporter"] is True
    assert main._is_supporter("alice") is True


def _stripe_event(tier: str, amount_total: int, username="alice") -> bytes:
    import json as _json
    return _json.dumps({
        "id": "evt_test_supporter",
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"username": username, "tier": tier},
            "client_reference_id": username,
            "payment_status": "paid",
            "amount_total": amount_total,
        }},
    }).encode()


def _sign(payload: bytes) -> str:
    """Samma HMAC-signatur som Stripe (och tests/test_stripe_billing.py)."""
    import hashlib
    import hmac as _hmac
    import time as _time
    ts = str(int(_time.time()))
    sig = _hmac.new(b"whsec_test123", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"