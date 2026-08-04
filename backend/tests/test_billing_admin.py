"""FAS D: admin billing + top-up — ledger, MRR, top-up, reset, subscription.

Täcker:
  - ledger-helpers: _ledger_load skapar tom fil, _ledger_append backfilla:r
    nycklar, _ledger_per_user summerar, _ledger_totals → mrr/transactions/total
  - MRR räknar bara AKTIV premium (utgången demote:as, räknas inte)
  - GET /api/admin/billing: shape, senaste 50 rader, tom ledger, 403 icke-admin
  - PUT turn-topup: bonus adderas kumulativt, förbrukas före cap-turns,
    validering (0/negativ → 400, okänd användare → 404, icke-admin → 403)
  - PUT turn-reset: turns_used=0, bonus behålls, 404/403
  - PUT subscription: premium → turn_cap 0 + oändliga turns; free →
    DEFAULT_TURN_CAP om cap:et var 0 (manuellt cap behålls), validering
  - /api/admin/stats innehåller FAS D-fält (subscription_status, turn_bonus,
    period_turns_used, revenue)

Ingen riktig data rörs: users.json + billing-ledgern pekas om till tmp
(auth.USERS_FILE, main._LEDGER_FILE) och kampanj-data till tmp
(state_manager.CAMPAIGNS_DIR + main.CAMPAIGNS_DIR).
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
from auth import create_token, hash_password  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    """Peka users.json mot tmp-fil (load_users/save_users i auth.py).

    autouse: ALLA tester i denna modul får skyddet — även de som anropar
    _seed_admin()/_seed_player() utan att be om fixturen. Utan autouse
    skrev testerna över den RIKTIGA users.json (bugg 2026-08-04).
    """
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    """Peka billing-ledgern mot tmp-fil (main._LEDGER_FILE)."""
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture
def campaigns_dir(tmp_path, monkeypatch):
    """Peka kampanj-data mot tmp-mapp (state_manager + main)."""
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def client(users_file, ledger_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── Hjälpare ─────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed_admin():
    main.save_users({
        "the_admin": {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0},
    })


def _seed_player(username="alice", **fields):
    users = main.load_users()
    u = users.setdefault(username, {
        "password_hash": hash_password("secret123"),
        "role": "player",
        "turn_cap": main.DEFAULT_TURN_CAP,
        "turns_used": 0,
        "turn_bonus": 0,
        "reset_date": _today(),
        "subscription_status": "free",
        "subscription_until": None,
    })
    u.update(fields)
    main.save_users(users)


def _atok() -> str:
    return create_token("the_admin", "admin")


def _ptok() -> str:
    return create_token("alice", "player")


# ── Ledger-helpers ───────────────────────────────────────────────────────

def test_ledger_load_creates_empty_file(ledger_file):
    assert main._ledger_load() == []
    assert ledger_file.exists()


def test_ledger_append_and_totals(ledger_file):
    _seed_admin()
    _seed_player("alice", subscription_status="tier2", subscription_until=_in_days(30), turn_cap=0)
    row = main._ledger_append({"user": "alice", "amount_sek": 105, "type": "stripe:tier2",
                               "stripe_sub_id": "sub_1", "event_id": "evt_1"})
    assert row["ts"]  # backfillad med _now_iso()
    assert row["user"] == "alice"
    assert row["amount_sek"] == 105
    assert main._ledger_per_user() == {"alice": 105}
    totals = main._ledger_totals()
    assert totals["mrr"] == 105         # 1 aktiv betald tier2 (stripe-rad i ledgern)
    assert totals["transactions"] == 1
    assert totals["total"] == 105
    # fler rader summeras per user + saknade nycklar backfillas med None
    main._ledger_append({"user": "alice", "amount_sek": 105, "type": "stripe:renewal"})
    main._ledger_append({"user": "bob", "amount_sek": 10, "type": "topup"})
    assert main._ledger_per_user() == {"alice": 210, "bob": 10}
    totals = main._ledger_totals()
    assert totals["transactions"] == 3
    assert totals["total"] == 220
    assert totals["mrr"] == 105         # bob är free, renewal dubblar inte MRR


def test_mrr_counts_only_active_premium(ledger_file):
    _seed_admin()
    _seed_player("active", subscription_status="tier2", subscription_until=_in_days(10))
    _seed_player("expired", subscription_status="tier2", subscription_until=_in_days(-1))
    _seed_player("freebie")
    # Bara riktiga Stripe-betalningar räknas — admin-given tier (ingen ledger-rad) ger INGEN MRR.
    main._ledger_append({"user": "active", "amount_sek": 105, "type": "stripe:tier2",
                         "stripe_sub_id": "sub_a", "event_id": "evt_a"})
    main._ledger_append({"user": "expired", "amount_sek": 105, "type": "stripe:tier2",
                         "stripe_sub_id": "sub_e", "event_id": "evt_e"})
    totals = main._ledger_totals()
    assert totals["mrr"] == 105  # active betald+aktiv; expired utgången; freebie ingen betalning


def test_mrr_ignores_admintier_without_payment(ledger_file):
    """Admin-given tier via setTier skriver inget till ledgern → MRR 0 trots premium-status."""
    _seed_admin()
    _seed_player("granted", subscription_status="tier2", subscription_until=_in_days(30))
    totals = main._ledger_totals()
    assert totals["mrr"] == 0
    assert totals["transactions"] == 0
    assert totals["total"] == 0


def test_mrr_includes_tier1_and_excludes_lifetime(ledger_file):
    """tier1 (3 €) + tier2 (9 €) räknas i MRR; lifetime är engångsintäkt."""
    _seed_admin()
    _seed_player("t1", subscription_status="tier1", subscription_until=_in_days(10))
    _seed_player("t2", subscription_status="tier2", subscription_until=_in_days(10))
    _seed_player("life", subscription_status="lifetime", subscription_until=_in_days(3650))
    main._ledger_append({"user": "t1", "amount_sek": 35, "type": "stripe:tier1", "event_id": "evt_t1"})
    main._ledger_append({"user": "t2", "amount_sek": 105, "type": "stripe:tier2", "event_id": "evt_t2"})
    main._ledger_append({"user": "life", "amount_sek": 1170, "type": "stripe:lifetime", "event_id": "evt_lt"})
    totals = main._ledger_totals()
    assert totals["mrr"] == 35 + 105
    assert totals["total"] == 35 + 105 + 1170  # lifetime ligger i total, ej i MRR


def test_ledger_corrupt_file_is_empty(ledger_file):
    ledger_file.write_text("{not json", encoding="utf-8")
    assert main._ledger_load() == []


# ── GET /api/admin/billing ───────────────────────────────────────────────

def test_billing_endpoint_shape(client, ledger_file):
    _seed_admin()
    _seed_player("alice", subscription_status="tier2", subscription_until=_in_days(30), turn_cap=0)
    main._ledger_append({"user": "alice", "amount_sek": 105, "type": "stripe:tier2", "event_id": "evt_1"})
    main._ledger_append({"user": "alice", "amount_sek": 105, "type": "stripe:renewal", "event_id": "evt_2"})
    main._ledger_append({"user": "alice", "amount_sek": 105, "type": "stripe:renewal", "event_id": "evt_3"})
    r = client.get("/api/admin/billing", cookies={"morkrets_token": _atok()})
    assert r.status_code == 200
    body = r.json()
    assert body["mrr"] == 105
    assert body["transactions"] == 3
    assert body["total"] == 315
    assert body["per_user"] == {"alice": 315}
    assert len(body["ledger"]) == 3
    assert body["ledger"][0]["amount_sek"] == 105


def test_billing_ledger_last_50(client, ledger_file):
    _seed_admin()
    for _ in range(55):
        main._ledger_append({"user": "alice", "amount_sek": 1, "type": "test"})
    r = client.get("/api/admin/billing", cookies={"morkrets_token": _atok()})
    body = r.json()
    assert body["transactions"] == 55
    assert len(body["ledger"]) == 50


def test_billing_empty_ledger(client, ledger_file):
    _seed_admin()
    r = client.get("/api/admin/billing", cookies={"morkrets_token": _atok()})
    assert r.status_code == 200
    assert r.json() == {"mrr": 0, "transactions": 0, "total": 0, "per_user": {}, "ledger": []}


def test_billing_403_non_admin(client):
    _seed_player()
    r = client.get("/api/admin/billing", cookies={"morkrets_token": _ptok()})
    assert r.status_code == 403


# ── Top-up ───────────────────────────────────────────────────────────────

def test_topup_grants_bonus(client):
    _seed_admin()
    _seed_player()
    r = client.put("/api/admin/user/alice/turn-topup", json={"bonus": 10},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    assert r.json()["turn_bonus"] == 10
    assert main.load_users()["alice"]["turn_bonus"] == 10
    # kumulativt
    r = client.put("/api/admin/user/alice/turn-topup", json={"bonus": 5},
                   cookies={"morkrets_token": _atok()})
    assert r.json()["turn_bonus"] == 15


def test_topup_consumed_first(client):
    """bonus förbrukas före cap-turns (via _turns_available)."""
    _seed_admin()
    _seed_player("alice", turn_cap=1, turn_bonus=0, turns_used=0)
    client.put("/api/admin/user/alice/turn-topup", json={"bonus": 100},
               cookies={"morkrets_token": _atok()})
    assert main._turns_available("alice") == 101
    # 1 förbrukad → cap-sloten gick först, bonusen orörd
    users = main.load_users()
    users["alice"]["turns_used"] = 1
    main.save_users(users)
    assert main._turns_available("alice") == 100


def test_topup_validation_and_404(client):
    _seed_admin()
    _seed_player()
    for bad in (0, -5):
        r = client.put("/api/admin/user/alice/turn-topup", json={"bonus": bad},
                       cookies={"morkrets_token": _atok()})
        assert r.status_code == 400, bad
    r = client.put("/api/admin/user/ghost/turn-topup", json={"bonus": 5},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 404


def test_topup_403_non_admin(client):
    _seed_player()
    r = client.put("/api/admin/user/alice/turn-topup", json={"bonus": 5},
                   cookies={"morkrets_token": _ptok()})
    assert r.status_code == 403


# ── Turn-reset ───────────────────────────────────────────────────────────

def test_turn_reset(client):
    _seed_admin()
    _seed_player("alice", turns_used=7, turn_bonus=3)
    r = client.put("/api/admin/user/alice/turn-reset", cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    assert r.json()["turns_used"] == 0
    u = main.load_users()["alice"]
    assert u["turns_used"] == 0
    assert u["turn_bonus"] == 3  # bonus behålls vid reset
    assert main._turns_available("alice") == main.DEFAULT_TURN_CAP + 3


def test_turn_reset_404_and_403(client):
    _seed_admin()
    _seed_player()
    r = client.put("/api/admin/user/ghost/turn-reset", cookies={"morkrets_token": _atok()})
    assert r.status_code == 404
    r = client.put("/api/admin/user/alice/turn-reset", cookies={"morkrets_token": _ptok()})
    assert r.status_code == 403


# ── Subscription ─────────────────────────────────────────────────────────

def test_subscription_grant_premium_and_revert(client):
    _seed_admin()
    _seed_player("alice", turn_cap=50)
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "tier2", "until": _in_days(30)},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscription_status"] == "tier2"
    assert body["turn_cap"] == main.DEFAULT_TURN_CAP  # tier2 = 50 turns / 6 h
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "tier2"
    assert u["subscription_until"] == _in_days(30)
    assert main._tier_for("alice") == "tier2"

    # tillbaka till free → DEFAULT_TURN_CAP återställs (cap:et var 0)
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "free", "until": None},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "free"
    assert u["subscription_until"] is None
    assert u["turn_cap"] == main.DEFAULT_TURN_CAP
    assert main._tier_for("alice") == "free"


def test_subscription_lifetime_unlimited(client):
    """lifetime → turn_cap 0 = oändliga turns."""
    _seed_admin()
    _seed_player("alice", turn_cap=50)
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "lifetime", "until": _in_days(3650)},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    assert r.json()["turn_cap"] == 0
    assert main._tier_for("alice") == "lifetime"
    assert main._turns_available("alice") == 999999


def test_subscription_tier1_sets_reset_ts(client):
    """tier1 → 50 turns / 6 h: reset_ts sätts om det saknas."""
    _seed_admin()
    _seed_player("alice", turn_cap=50)
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "tier1", "until": _in_days(30)},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200, r.text
    u = main.load_users()["alice"]
    assert u["subscription_status"] == "tier1"
    assert u.get("reset_ts")  # sätts för 6-timmars-period
    assert main._tier_for("alice") == "tier1"
    assert main._turns_available("alice") == main.DEFAULT_TURN_CAP


def test_subscription_keeps_custom_cap_on_revert(client):
    """free-revert ändrar INTE ett manuellt satt cap > 0."""
    _seed_admin()
    _seed_player("alice", turn_cap=25)
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "free", "until": None},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200
    assert main.load_users()["alice"]["turn_cap"] == 25


def test_subscription_validation_404_403(client):
    _seed_admin()
    _seed_player()
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "gold", "until": None},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 400
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "premium", "until": "not-a-date"},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 400
    r = client.put("/api/admin/user/ghost/subscription",
                   json={"status": "premium", "until": _in_days(30)},
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 404
    r = client.put("/api/admin/user/alice/subscription",
                   json={"status": "premium", "until": _in_days(30)},
                   cookies={"morkrets_token": _ptok()})
    assert r.status_code == 403


# ── Admin-stats innehåller FAS D-fält ────────────────────────────────────

def test_admin_stats_has_billing_fields(client, ledger_file):
    _seed_admin()
    _seed_player("alice", subscription_status="tier2", subscription_until=_in_days(30),
                 turn_cap=50, turn_bonus=4, turns_used=2)
    main._ledger_append({"user": "alice", "amount_sek": 105, "type": "invoice.paid"})
    r = client.get("/api/admin/stats", cookies={"morkrets_token": _atok()})
    assert r.status_code == 200
    row = next(u for u in r.json()["users"] if u["username"] == "alice")
    assert row["subscription_status"] == "tier2"
    assert row["subscription_until"] == _in_days(30)
    assert row["turn_bonus"] == 4
    assert row["period_turns_used"] == 2
    assert row["revenue"] == 105
