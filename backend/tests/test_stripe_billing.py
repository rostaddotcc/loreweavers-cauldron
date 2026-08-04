"""Stripe — checkout + webhook (2026-08-04).

autouse-fixtures: ALLA tester pekar users.json, kampanjer, ledger mot tmp.
Stripe-REST mockas via monkeypatch av main._stripe_post; webhook-signaturer
genereras med hmac (samma algoritm som Stripe). ALDRIG riktig data.
"""
import hashlib
import hmac
import json
import sys
import time
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


@pytest.fixture(autouse=True)
def outbox_dir(tmp_path, monkeypatch):
    d = tmp_path / "outbox"
    monkeypatch.setattr(main, "OUTBOX_DIR", d)
    return d


@pytest.fixture(autouse=True)
def stripe_env(monkeypatch):
    """Sätt Stripe-värden så endpoints är aktiva i tester."""
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", "whsec_test123")
    monkeypatch.setattr(main, "STRIPE_PRICES", {
        "tier1": "price_t1", "tier2": "price_t2", "lifetime": "price_lt",
    })


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, outbox_dir, stripe_env):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", tier="free"):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": role,
                   "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": "2026-08-04", "subscription_status": tier,
                   "subscription_until": None},
    })


def _seed_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _sign(payload: bytes) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_test123", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event(etype, obj, event_id="evt_1"):
    return json.dumps({"id": event_id, "type": etype, "data": {"object": obj}}).encode()


# ── Checkout ─────────────────────────────────────────────────────────

def test_checkout_requires_login(client):
    r = client.post("/api/billing/checkout", json={"tier": "tier2"})
    assert r.status_code == 401


def test_checkout_unknown_tier_400(client):
    _seed()
    r = client.post("/api/billing/checkout", json={"tier": "gold"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 400


def test_checkout_tier2_returns_stripe_url(client, monkeypatch):
    _seed()
    captured = {}

    async def fake_post(path, data):
        captured["path"] = path
        captured["data"] = data
        return {"url": "https://checkout.stripe.com/c/pay/test123", "id": "cs_1"}

    monkeypatch.setattr(main, "_stripe_post", fake_post)
    r = client.post("/api/billing/checkout", json={"tier": "tier2"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert "checkout.stripe.com" in r.json()["url"]
    assert captured["path"] == "checkout/sessions"
    assert captured["data"]["mode"] == "subscription"
    assert captured["data"]["line_items[0][price]"] == "price_t2"
    assert captured["data"]["metadata[username]"] == "alice"
    # Åtkomst ges INTE i checkout-svaret — users.json orörd
    assert main.load_users()["alice"]["subscription_status"] == "free"


def test_checkout_lifetime_uses_payment_mode(client, monkeypatch):
    _seed()
    captured = {}

    async def fake_post(path, data):
        captured["mode"] = data["mode"]
        return {"url": "https://checkout.stripe.com/c/pay/x"}

    monkeypatch.setattr(main, "_stripe_post", fake_post)
    r = client.post("/api/billing/checkout", json={"tier": "lifetime"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert captured["mode"] == "payment"


# ── Webhook: signatur ────────────────────────────────────────────────

def test_webhook_rejects_bad_signature(client):
    r = client.post("/api/stripe/webhook", content=_event("checkout.session.completed", {}),
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400


def test_webhook_rejects_no_signature(client):
    r = client.post("/api/stripe/webhook", content=_event("checkout.session.completed", {}))
    assert r.status_code == 400


def test_webhook_tampered_body_rejected(client):
    body = _event("checkout.session.completed", {"amount_total": 900})
    good = _sign(body)
    tampered = body.replace(b"900", b"999")
    r = client.post("/api/stripe/webhook", content=tampered,
                    headers={"stripe-signature": good})
    assert r.status_code == 400


# ── Webhook: checkout.session.completed ──────────────────────────────

def test_webhook_checkout_tier2_grants_access(client):
    _seed()
    _seed_campaign("alice")
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "tier2"},
        "client_reference_id": "alice",
        "payment_status": "paid",
        "customer": "cus_123",
        "subscription": "sub_123",
        "amount_total": 900,
    }, event_id="evt_completed")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "tier2"
    assert u["stripe_customer_id"] == "cus_123"
    assert u["stripe_subscription_id"] == "sub_123"
    assert u["turn_cap"] == 50
    assert u["reset_ts"]
    # Ledger-rad + chattlogg
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert any(e["type"] == "stripe:tier2" and e["user"] == "alice" for e in ledger)
    state = main.store.get("alice")
    trans = main.store.load_transcript(state, last_n=10)
    assert any("upgraded as a token of appreciation" in e["content"] for e in trans)


def test_webhook_checkout_lifetime(client):
    _seed()
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "lifetime"},
        "payment_status": "paid", "amount_total": 10000,
    }, event_id="evt_lt")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "lifetime"
    assert u["subscription_until"] is None
    assert u["turn_cap"] == 0


def test_webhook_checkout_unknown_user_ignored(client):
    body = _event("checkout.session.completed", {
        "metadata": {"username": "ghost", "tier": "tier2"},
        "payment_status": "paid",
    })
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200


def test_webhook_unpaid_checkout_ignored(client):
    _seed()
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "tier2"},
        "payment_status": "unpaid",
    })
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    assert main.load_users()["alice"]["subscription_status"] == "free"


# ── Webhook: subscription.deleted + invoice.paid ─────────────────────

def test_webhook_subscription_deleted_demotes(client):
    _seed("alice", tier="tier2")
    u = main.load_users()
    u["alice"]["stripe_customer_id"] = "cus_123"
    u["alice"]["stripe_subscription_id"] = "sub_123"
    u["alice"]["subscription_until"] = "2026-09-04"
    main.save_users(u)
    body = _event("customer.subscription.deleted",
                  {"id": "sub_123", "customer": "cus_123"})
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "free"
    assert u["subscription_until"] is None
    assert u["turn_cap"] == 50


def test_webhook_invoice_paid_extends(client):
    _seed("alice", tier="tier2")
    u = main.load_users()
    u["alice"]["stripe_subscription_id"] = "sub_123"
    u["alice"]["subscription_until"] = "2026-09-04"
    main.save_users(u)
    body = _event("invoice.paid",
                  {"subscription": "sub_123", "amount_paid": 900})
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    assert main.load_users()["alice"]["subscription_until"] == "2026-10-04"
