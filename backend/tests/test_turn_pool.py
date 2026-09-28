"""Turn-pott per spelare (2026-09-28) — hinkar, livstidsräknare, grant-ledger.

Varför den finns: potten spenderas promo → daglig cap → köpta, cap-räknaren
nollställs varje dygn och turn-ledgern saknade hink. "Hur mycket har spelaren
köpt / hur mycket har gått åt, free vs paid" gick därför inte att svara på.

Täcker:
  - spenderingsordningen ger rätt `bucket` (promo → free → paid) och rätt
    livstidsräknare per hink
  - livstidsräknarna överlever dygns-rollovern (turns_used nollas, *_total ej)
  - admin-turn-reset nollställer perioden men rör INTE livstidsräknarna
  - `_turn_pool().available` == `_turns_available()` (hård invariant)
  - cap 0 = oändlig pott (None/999999, aldrig "0 av 0")
  - grant-ledgern: summor, källor, granted_known (opening_balance ≠ köp)
  - ledger-rader bär bucket + pool_after; gamla rader utan bucket = unknown

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger + grant-fil
mot tmp — ALDRIG riktig data.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402

TODAY = datetime.now(timezone.utc).date()


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
def turn_ledgers_dir(tmp_path, monkeypatch):
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


def _seed(username="alice", **fields):
    """Seeda ett konto DIREKT i users.json (ingen HTTP, ingen rate-limit)."""
    users = main.load_users()
    u = {
        "password_hash": hash_password("secret123"), "role": "player",
        "turn_cap": main.DEFAULT_TURN_CAP, "turns_used": 0,
        "turn_bonus": 0, "promo_bonus": 0,
        "reset_date": TODAY.isoformat(),
        "subscription_status": "free", "features": {},
    }
    u.update(fields)
    users[username] = u
    main.save_users(users)
    return u


def _user(username="alice") -> dict:
    return main.load_users().get(username, {})


def _consume(username="alice", n=1, action="dm"):
    """Förbruka n turns och returnera hinkarna i ordning."""
    return [main._consume_turn(username, action=action) for _ in range(n)]


def _admin_token(username="the_admin"):
    users = main.load_users()
    users[username] = {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 30}
    main.save_users(users)
    return create_token(username, "admin")


# ── spenderingsordning + hink ────────────────────────────────────────────────

def test_bucket_order_promo_then_free_then_paid():
    _seed(promo_bonus=2, turn_cap=3, turn_bonus=2)
    buckets = _consume(n=5)
    assert buckets == ["promo", "promo", "free", "free", "free"]
    u = _user()
    assert u["promo_bonus"] == 0
    assert u["turns_used"] == 3
    assert u["turn_bonus"] == 2  # köpta rörs först när capen är slut
    assert (u["turns_used_promo_total"], u["turns_used_free_total"]) == (2, 3)


def test_paid_bucket_is_used_only_after_cap_is_spent():
    _seed(turn_cap=1, turn_bonus=2)
    assert _consume(n=3) == ["free", "paid", "paid"]
    u = _user()
    assert u["turn_bonus"] == 0
    assert u["turns_used_paid_total"] == 2
    assert main._turn_pool("alice", udata=u)["paid"]["used_total"] == 2


def test_promo_absorbs_turns_so_free_counter_stays_zero():
    """Diagnosen i planen: 92 konton har legacy-promo kvar, så "0/30 använt"
    betyder INTE "spelade inget" — allt gick i promo-hinken."""
    _seed(promo_bonus=300, turn_cap=30)
    _consume(n=5)
    u = _user()
    assert u["turns_used"] == 0
    assert u["turns_used_free_total"] == 0
    assert u["turns_used_promo_total"] == 5
    pool = main._turn_pool("alice", udata=u)
    assert pool["promo"]["left"] == 295
    assert pool["used_lifetime"]["promo"] == 5
    assert pool["free"]["used_period"] == 0


# ── livstidsräknare vs rollover ──────────────────────────────────────────────

def test_lifetime_counters_survive_daily_rollover():
    _seed(turn_cap=30)
    _consume(n=2)
    # Spola tillbaka reset_date → nästa anrop rullar perioden
    users = main.load_users()
    users["alice"]["reset_date"] = (TODAY - timedelta(days=1)).isoformat()
    main.save_users(users)

    assert _consume(n=1) == ["free"]       # rollover hände i samma anrop
    u = _user()
    assert u["turns_used"] == 1            # perioden nollställd
    assert u["turns_used_free_total"] == 3  # livstiden orörd


def test_admin_turn_reset_keeps_lifetime_counters():
    from fastapi.testclient import TestClient
    _seed(turn_cap=30)
    _consume(n=4)
    atok = _admin_token()
    with TestClient(main.app) as client:
        r = client.put("/api/admin/user/alice/turn-reset", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    u = _user()
    assert u["turns_used"] == 0
    assert u["turns_used_free_total"] == 4  # reset ger gratis turns, inte amnesti


def test_undo_consumes_a_turn_without_refund_tracking():
    """Undo kostar 1 turn (beslut 2026-09-09, ingen refund) — räknarna ska bara
    fortsätta uppåt, ingen återläggningslogik finns."""
    _seed(turn_cap=30)
    _consume(n=1, action="dm")
    _consume(n=1, action="undo")
    u = _user()
    assert u["turns_used"] == 2
    assert u["turns_used_free_total"] == 2


# ── pott == gate (hård invariant) ────────────────────────────────────────────

def test_pool_available_equals_turn_gate():
    _seed(promo_bonus=10, turn_cap=30, turn_bonus=5)
    _consume(n=4)
    pool = main._turn_pool("alice")
    assert pool["available"] == main._turns_available("alice")
    assert pool["available"] == 10 + 26 + 5


def test_unlimited_account_reports_infinity_not_zero():
    _seed(turn_cap=0, subscription_status="lifetime")
    _consume(n=3)
    pool = main._turn_pool("alice")
    assert pool["free"]["unlimited"] is True
    assert pool["free"]["left_period"] is None
    assert pool["available"] is None
    assert main._turns_available("alice") == 999999  # gaten säger ∞, inte 0
    assert main._turn_pool("alice")["used_lifetime"]["free"] == 3


def test_pool_buckets_sum_to_available():
    _seed(promo_bonus=7, turn_cap=30, turn_bonus=3)
    _consume(n=2)
    pool = main._turn_pool("alice")
    total = pool["free"]["left_period"] + pool["promo"]["left"] + pool["paid"]["left"]
    assert total == pool["available"]


# ── grant-ledgern ("hur mycket köpte spelaren") ───────────────────────────────

def test_grant_ledger_sums_and_sources():
    _append = main._append_turn_grant
    assert _append("bob", 100, "stripe:unlock10") is True
    assert _append("bob", 300, "stripe:support300") is True
    assert _append("bob", 0, "stripe:donation") is False   # 0 turns bokförs inte
    idx = main._turn_grants_index()
    assert idx["bob"]["turns"] == 400
    assert idx["bob"]["rows"] == 2
    assert set(idx["bob"]["sources"]) == {"stripe:unlock10", "stripe:support300"}
    assert [r["turns"] for r in main._read_turn_grants("bob")] == [100, 300]


def test_granted_known_is_false_for_opening_balance_only():
    """En opening_balance-rad är ett bokslut, inte ett köp — UI:t ska visa
    "köpt: okänt före <datum>" i stället för att påstå ett köp."""
    _seed(turn_bonus=300)
    main._append_turn_grant("alice", 300, "opening_balance", note="migration")
    pool = main._turn_pool("alice")
    assert pool["paid"]["granted"] == 300
    assert pool["paid"]["granted_known"] is False
    main._append_turn_grant("alice", 100, "stripe:unlock10")
    pool2 = main._turn_pool("alice")
    assert pool2["paid"]["granted"] == 400
    assert pool2["paid"]["granted_known"] is True


def test_pool_without_grants_is_honest_about_unknown_purchases():
    _seed(turn_bonus=300)  # kontot har köpta turns men ingen grant-rad
    pool = main._turn_pool("alice")
    assert pool["paid"]["left"] == 300
    assert pool["paid"]["granted"] == 0
    assert pool["paid"]["granted_known"] is False
    assert pool["data_since"] is None


# ── ledgern: hink per turn ───────────────────────────────────────────────────

def test_ledger_rows_carry_bucket_and_pool_after():
    _seed(turn_cap=30, turn_bonus=2)
    _consume(n=1)
    rows = main._read_turn_ledger("alice")
    assert len(rows) == 1
    assert rows[0]["bucket"] == "free"
    assert rows[0]["pool_after"] == 31  # 29 kvar i capen + 2 köpta


def test_legacy_ledger_rows_without_bucket_count_as_unknown():
    (main._TURN_LEDGERS_DIR).mkdir(parents=True, exist_ok=True)
    p = main._TURN_LEDGERS_DIR / "old.jsonl"
    p.write_text('{"ts": "2026-08-10T10:00:00+00:00", "action": "dm", "model": null, "tokens": 0}\n'
                 '{"ts": "2026-09-28T10:00:00+00:00", "action": "dm", "model": null, "tokens": 0, "bucket": "paid"}\n',
                 encoding="utf-8")
    bd = main._turn_ledger_bucket_breakdown("old")
    assert bd == {"promo": 0, "free": 0, "paid": 1, "unknown": 1}
    assert main._turn_ledger_bucket_breakdown("old", since=TODAY.isoformat())["unknown"] == 0


def test_pool_after_is_none_for_unlimited_accounts():
    _seed(turn_cap=0)
    _consume(n=1)
    assert main._read_turn_ledger("alice")[0]["pool_after"] is None


# ── API-kontrakt ────────────────────────────────────────────────────────────

def test_admin_user_detail_exposes_pool_grants_and_coding():
    from fastapi.testclient import TestClient
    _seed(turn_cap=30, promo_bonus=5, turn_bonus=7)
    atok = _admin_token()
    with TestClient(main.app) as client:
        r = client.get("/api/admin/user/alice", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    body = r.json()
    # PLATT pott-form (samma nycklar som overview-raden) + dossierns extra fält.
    assert body["turn_pool"]["promo_left"] == 5
    assert body["turn_pool"]["paid_left"] == 7
    assert body["turn_pool"]["available"] == main._turns_available("alice")
    assert body["turn_pool"]["used_lifetime"] == {"free": 0, "paid": 0, "promo": 0, "unknown": 0}
    assert body["turn_pool"]["tracked_since"] == main.POOL_TRACKING_SINCE
    assert body["coding"]["code"] == "granted"
    assert body["coding"]["why"]
    assert isinstance(body["turn_grants"], list)
    assert body["turn_ledger_buckets"]["unknown"] == 0


def test_overview_row_and_dossier_agree_on_the_pool():
    """EN sanning: overview-raden och dossién ska svara exakt samma pott-tal —
    annars kan tabellen och dossién visa olika saker om samma spelare."""
    from fastapi.testclient import TestClient
    _seed(turn_cap=30, promo_bonus=5, turn_bonus=7)
    main._append_turn_grant("alice", 300, "stripe:support300")
    _consume(n=3)
    atok = _admin_token()
    with TestClient(main.app) as client:
        rows = client.get("/api/admin/overview?window=all", cookies={"morkrets_token": atok}).json()["users"]
        row = [r for r in rows if r["username"] == "alice"][0]
        detail = client.get("/api/admin/user/alice", cookies={"morkrets_token": atok}).json()
    flat = main._pool_compact(main._turn_pool("alice"))
    assert row["turn_pool"] == flat
    for k, v in flat.items():
        assert detail["turn_pool"][k] == v, k
    assert row["coding"]["code"] == detail["coding"]["code"]
    assert row["turn_pool"]["available"] == main._turns_available("alice")


def test_admin_ledger_endpoint_exposes_bucket_split():
    from fastapi.testclient import TestClient
    _seed(turn_cap=30)
    _consume(n=2)
    atok = _admin_token()
    with TestClient(main.app) as client:
        r = client.get("/api/admin/user/alice/ledger", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by_bucket"]["free"] == 2
    assert body["by_bucket_today"]["free"] == 2
    assert body["entries"][0]["bucket"] == "free"


def test_topup_endpoint_writes_a_grant_row():
    from fastapi.testclient import TestClient
    _seed(turn_cap=30)
    atok = _admin_token()
    with TestClient(main.app) as client:
        r = client.put("/api/admin/user/alice/turn-topup", json={"bonus": 300},
                       cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    idx = main._turn_grants_index()
    assert idx["alice"]["turns"] == 300
    assert idx["alice"]["sources"] == ["admin"]
    pool = main._turn_pool("alice")
    assert pool["paid"]["left"] == 300
    assert pool["paid"]["granted_known"] is True


def test_unknown_user_pool_is_empty_not_a_crash():
    pool = main._turn_pool("nobody")
    assert pool["available"] == 0 or pool["available"] is None
    assert pool["paid"]["left"] == 0
    assert main._consume_turn("nobody") == "none"
