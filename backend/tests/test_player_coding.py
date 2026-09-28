"""Free/paid-kodning (2026-09-28, rostad) — Paid / Granted / Free.

rostad: "spelare i dashboarden ska kodas med free/paid tiers". Tre koder, för
två vore oärligt: 7 konton hade 300 turns kvar utan en enda betalningsrad.
Kodningen räknas server-side (EN funktion) så tabell, mobilkort, dossier,
Recently active, drawer och CSV aldrig kan säga olika saker.

Live-facit 2026-09-28 mot skarp users.json + betalningsledgern (verifierat med
curl mot containern): paid 7 · granted 98 · free 54 av 159 konton — det är
matrisen nedan som gäller, räknad mot fixtures här.

autouse-fixtures: users.json + kampanjer + ledger + grant-fil pekas mot tmp.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402

TODAY = datetime.now(timezone.utc).date().isoformat()


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


def _seed(username, **fields):
    users = main.load_users()
    u = {
        "password_hash": "x", "role": "player", "turn_cap": main.DEFAULT_TURN_CAP,
        "turns_used": 0, "turn_bonus": 0, "promo_bonus": 0, "reset_date": TODAY,
        "subscription_status": "free", "features": {},
    }
    u.update(fields)
    users[username] = u
    main.save_users(users)
    return u


def _code(username, revenue=0, tier=None):
    return main._player_coding(username, revenue=revenue,
                               pool=main._turn_pool(username),
                               tier=tier or main._tier_for(username))


def test_plain_free_account_is_coded_free():
    _seed("frida")
    c = _code("frida")
    assert c["code"] == "free"
    assert c["paid"] is False and c["granted"] is False
    assert "free quota" in c["why"]


def test_paying_account_with_billing_row_is_coded_paid():
    _seed("pelle")
    c = _code("pelle", revenue=70)
    assert c["code"] == "paid"
    assert c["paid"] is True
    assert c["why"] == "70 kr paid"


def test_grant_without_a_payment_row_is_granted_never_paid():
    """Kärnfallet: 300 turns kvar, noll betalningsrader (7 konton 2026-09-28)."""
    _seed("gustav", turn_bonus=300)
    c = _code("gustav", revenue=0)
    assert c["code"] == "granted"
    assert c["paid"] is False
    assert "300" in c["why"]


def test_legacy_promo_account_is_coded_granted():
    _seed("greta", promo_bonus=300)
    c = _code("greta")
    assert c["code"] == "granted"
    assert "promo" in c["why"]


def test_non_default_cap_is_coded_granted():
    _seed("boblin", turn_cap=300)
    c = _code("boblin")
    assert c["code"] == "granted"
    assert "cap 300" in c["why"]


def test_unlimited_lifetime_account_is_coded_paid():
    _seed("liv", turn_cap=0, subscription_status="lifetime")
    c = _code("liv", tier="lifetime")
    assert c["code"] == "paid"
    assert c["tier"] == "lifetime"


def test_paid_tier2_without_billing_row_is_still_paid():
    _seed("chupish", turn_cap=main.PATRON_DAILY_CAP)
    c = _code("chupish", tier="tier2")
    assert c["code"] == "paid"


def test_coding_does_not_change_when_turns_are_consumed():
    _seed("konsumerar", turn_bonus=100)
    before = _code("konsumerar")["code"]
    for _ in range(3):
        main._consume_turn("konsumerar")
    assert _code("konsumerar")["code"] == before == "granted"


def test_promo_spent_to_zero_still_codes_granted():
    """En spelare som bränt upp sin promo är inte "free" igen — historiken
    (livstidsräknaren) visar att kontot fick turns utöver gratiskvoten."""
    _seed("promobränd", promo_bonus=2)
    main._consume_turn("promobränd")
    main._consume_turn("promobränd")
    pool = main._turn_pool("promobränd")
    assert pool["promo"]["left"] == 0
    assert pool["promo"]["used_total"] == 2
    assert _code("promobränd")["code"] == "granted"
