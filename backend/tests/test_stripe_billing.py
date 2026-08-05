"""Stripe — checkout + webhook (2026-08-04).

autouse-fixtures: ALLA tester pekar users.json, kampanjer, ledger mot tmp.
Stripe-REST mockas via monkeypatch av main._stripe_post; webhook-signaturer
genereras med hmac (samma algoritm som Stripe). ALDRIG riktig data.
"""
import hashlib
import hmac
import json
import sys
from datetime import datetime, timedelta, timezone
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
def churn_file(tmp_path, monkeypatch):
    f = tmp_path / "_churn.json"
    monkeypatch.setattr(main, "_CHURN_FILE", f)
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
        "support300": "price_sup300", "patron500": "price_pat500",
        "donation": "", "lifetime": "price_lt",
    })


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, outbox_dir, stripe_env):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", tier="free", features=None):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": role,
                   "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": "2026-08-04", "subscription_status": tier,
                   "subscription_until": None,
                   "features": features or {},
                   "start_bonus_granted": True,
                   "email": "alice@example.com"},  # e-post krävs före köp (2026-08-04)
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
    r = client.post("/api/billing/checkout", json={"tier": "patron500"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert "checkout.stripe.com" in r.json()["url"]
    assert captured["path"] == "checkout/sessions"
    assert captured["data"]["mode"] == "payment"  # one-time — ingen subscription
    assert captured["data"]["line_items[0][price]"] == "price_pat500"
    assert captured["data"]["metadata[username]"] == "alice"
    # Åtkomst ges INTE i checkout-svaret — users.json orörd
    assert main.load_users()["alice"]["subscription_status"] == "free"


def test_checkout_support300_payment_mode(client, monkeypatch):
    _seed()
    captured = {}

    async def fake_post(path, data):
        captured["mode"] = data["mode"]
        captured["price"] = data.get("line_items[0][price]")
        return {"url": "https://checkout.stripe.com/c/pay/x"}

    monkeypatch.setattr(main, "_stripe_post", fake_post)
    r = client.post("/api/billing/checkout", json={"tier": "support300"},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert captured["mode"] == "payment"
    assert captured["price"] == "price_sup300"


def test_checkout_donation_custom_amount(client, monkeypatch):
    _seed()
    captured = {}

    async def fake_post(path, data):
        captured["data"] = data
        return {"url": "https://checkout.stripe.com/c/pay/x"}

    monkeypatch.setattr(main, "_stripe_post", fake_post)
    r = client.post("/api/billing/checkout", json={"tier": "donation", "amount": 5.0},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert captured["data"]["mode"] == "payment"
    assert captured["data"]["line_items[0][price_data][unit_amount]"] == "500"  # 5€ = 500 ören
    assert captured["data"]["line_items[0][price_data][product_data][name]"] == "Support the Cauldron"


def test_checkout_donation_bad_amount(client, monkeypatch):
    _seed()
    r = client.post("/api/billing/checkout", json={"tier": "donation", "amount": 0.5},
                    cookies={"morkrets_token": _tok()})
    assert r.status_code == 400


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

def test_webhook_checkout_patron500_grants_access(client):
    _seed()
    _seed_campaign("alice")
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "patron500"},
        "client_reference_id": "alice",
        "payment_status": "paid",
        "customer": "cus_123",
        "amount_total": 1000,
    }, event_id="evt_completed")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 500  # +500 turns
    assert u["features"]["export"] is True
    assert u["features"]["wan1080"] is True
    assert u["features"]["all_models"] is True
    # 2026-08-05 v2: hela förmånspaketet får features_until = +30 dagar
    # (enhetligt fönster, stackbart). models_until migreras bort.
    assert u["features_until"]
    assert "models_until" not in u
    expected = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    assert u["features_until"] == expected
    assert u["stripe_customer_id"] == "cus_123"
    assert u["turn_cap"] == 50  # 50/dag — INTE oändligt
    # Ledger-rad + chattlogg
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert any(e["type"] == "stripe:patron500" and e["user"] == "alice" for e in ledger)
    state = main.store.get("alice")
    trans = main.store.load_transcript(state, last_n=10)
    assert any("upgraded as a token of appreciation" in e["content"] for e in trans)


def test_webhook_checkout_support300_grants_export(client):
    """3€ Support: +300 turns + export (permanent) — inga premiummodeller."""
    _seed("alice")
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "support300"},
        "client_reference_id": "alice",
        "payment_status": "paid",
        "customer": "cus_s1",
        "amount_total": 300,
    }, event_id="evt_support")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 300
    assert u["features"]["export"] is True
    assert "all_models" not in u["features"]
    assert "wan1080" not in u["features"]
    assert main._tier_for("alice") == "tier1"  # Support
    # modellerna är FORTFARANDE klampade (Support = stepfun only)
    assert main._clamp_player_model("qwen3.8-max", tier="tier1") == "step-3.7-flash"


def test_webhook_checkout_donation_no_features(client):
    """Valfri summa: bara ledger — inga förmåner."""
    _seed("alice")
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "donation"},
        "client_reference_id": "alice",
        "payment_status": "paid",
        "amount_total": 500,
    }, event_id="evt_donation")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["turn_bonus"] == 0
    assert u["features"] == {}
    assert u["subscription_status"] == "free"
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert any(e["type"] == "stripe:donation" and e["user"] == "alice" for e in ledger)


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
        "metadata": {"username": "ghost", "tier": "patron500"},
        "payment_status": "paid",
    })
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200


def test_webhook_unpaid_checkout_ignored(client):
    _seed()
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "patron500"},
        "payment_status": "unpaid",
    })
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    assert main.load_users()["alice"]["turn_bonus"] == 0


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
    # Churn-datapoint: ledger-rad + per-dag-ackumulator (rostad 2026-08-04)
    ledger = main._ledger_load()
    churn_rows = [row for row in ledger if row.get("type") == "stripe:churn"]
    assert len(churn_rows) == 1
    assert churn_rows[0]["user"] == "alice"
    assert churn_rows[0]["amount_sek"] == 0
    churn = main._churn_load()
    today = datetime.now(timezone.utc).date().isoformat()
    assert churn.get(today) == 1
    # Churn-rader räknas inte som transaktioner
    totals = main._ledger_totals()
    assert totals["transactions"] == 0


def test_churn_record_in_billing_api(client):
    """/api/admin/billing exponerar churn per dag."""
    _seed("boss", role="admin")
    main._churn_record("alice", "sub_123")
    r = client.get("/api/admin/billing", cookies={"morkrets_token": _tok("boss", "admin")})
    assert r.status_code == 200
    data = r.json()
    today = datetime.now(timezone.utc).date().isoformat()
    assert data["churn"].get(today) == 1


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


# ── Webhook: idempotens (Stripe levererar om events) ─────────────────

def test_webhook_duplicate_checkout_not_granted_twice(client):
    _seed()
    _seed_campaign("alice")
    body = _event("checkout.session.completed", {
        "metadata": {"username": "alice", "tier": "patron500"},
        "client_reference_id": "alice",
        "payment_status": "paid",
        "customer": "cus_123",
        "amount_total": 1000,
    }, event_id="evt_dup")
    sig = _sign(body)
    r1 = client.post("/api/stripe/webhook", content=body,
                     headers={"stripe-signature": sig})
    assert r1.status_code == 200
    bonus_first = main.load_users()["alice"]["turn_bonus"]

    # Samma event levererat IGEN (Stripe-retry) — måste ignoreras helt.
    r2 = client.post("/api/stripe/webhook", content=body,
                     headers={"stripe-signature": sig})
    assert r2.status_code == 200
    assert r2.json() == {"received": True}

    u = main.load_users()["alice"]
    # Bonusen får INTE dubblas av dubbelleveransen.
    assert u["turn_bonus"] == bonus_first
    # Endast EN ledger-rad för eventet.
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert len([e for e in ledger if e["event_id"] == "evt_dup"]) == 1


def test_webhook_duplicate_invoice_paid_no_double_extend(client):
    _seed("alice", tier="tier2")
    u = main.load_users()
    u["alice"]["stripe_subscription_id"] = "sub_123"
    u["alice"]["subscription_until"] = "2026-09-04"
    main.save_users(u)
    body = _event("invoice.paid",
                  {"subscription": "sub_123", "amount_paid": 900},
                  event_id="evt_inv_dup")
    sig = _sign(body)
    client.post("/api/stripe/webhook", content=body,
                headers={"stripe-signature": sig})
    client.post("/api/stripe/webhook", content=body,
                headers={"stripe-signature": sig})
    # +30d en gång, inte två (annars skulle det bli 2026-11-03).
    assert main.load_users()["alice"]["subscription_until"] == "2026-10-04"
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert len([e for e in ledger if e["event_id"] == "evt_inv_dup"]) == 1


# ── Uppsägning via kundportalen (2026-08-04, test: nomis via kvittot) ─────

def _seed_subscribed(username="alice", sub_id="sub_123", tier="tier1"):
    u = main.load_users()
    u[username] = u.get(username, {})
    u[username].update({
        "password_hash": hash_password("secret123"), "role": "player",
        "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
        "reset_date": "2026-08-04", "subscription_status": tier,
        "subscription_until": "2026-11-02",
        "stripe_customer_id": "cus_123",
        "stripe_subscription_id": sub_id,
        "email": "alice@example.com",
    })
    main.save_users(u)


def test_webhook_cancel_scheduled_captures_intent(client):
    """customer.subscription.updated med cancel_at → flagga + ledger-rad direkt
    (annars väntar vi på deleted vid periodens slut)."""
    _seed_subscribed()
    body = _event("customer.subscription.updated",
                  {"id": "sub_123", "customer": "cus_123",
                   "cancel_at": 1788533572, "cancel_at_period_end": False},
                  event_id="evt_cancel_sched")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["cancel_scheduled_at"]
    # Förmånerna ska vara INTACTA till periodens slut (ingen demotion ännu)
    assert u["subscription_status"] == "tier1"
    assert u["turn_cap"] == 50
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert any(e["type"] == "stripe:cancel_scheduled" and e["user"] == "alice" for e in ledger)


def test_webhook_cancel_reverted_removes_flag(client):
    """cancel_at rensat (kunden ångrade sig i portalen) → flaggan tas bort."""
    _seed_subscribed()
    u = main.load_users()
    u["alice"]["cancel_scheduled_at"] = "2026-08-04T20:00:00"
    main.save_users(u)
    body = _event("customer.subscription.updated",
                  {"id": "sub_123", "customer": "cus_123",
                   "cancel_at": None, "cancel_at_period_end": False},
                  event_id="evt_cancel_revert")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    assert "cancel_scheduled_at" not in main.load_users()["alice"]
    ledger = json.loads(main._LEDGER_FILE.read_text())
    assert any(e["type"] == "stripe:cancel_reverted" for e in ledger)


def test_webhook_deleted_after_scheduled(client):
    """Vid periodens slut: deleted → riktig churn + flaggan rensas."""
    _seed_subscribed()
    u = main.load_users()
    u["alice"]["cancel_scheduled_at"] = "2026-08-04T20:00:00"
    main.save_users(u)
    body = _event("customer.subscription.deleted",
                  {"id": "sub_123", "customer": "cus_123"},
                  event_id="evt_sub_deleted")
    r = client.post("/api/stripe/webhook", content=body,
                    headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "free"
    assert "cancel_scheduled_at" not in u
    churn = json.loads(main._CHURN_FILE.read_text())
    assert sum(churn.values()) == 1
