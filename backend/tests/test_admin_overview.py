"""Admin dashboard v2 (2026-09-27, rostad): aggregeringslagret + overview-routen.

Täcker:
  - _revenue_breakdown: by_product (summerar EXAKT mot _ledger_totals()["total"]),
    "other"-bucketen, churn/cancel uteslutet, live-produkter med 0 kr,
    by_month/by_date i Europe/Stockholm (lokal månadsgräns), by_country ur
    iplog-cachen, customers sorterade på sek + payments-räkning
  - _value_delivered: turns ur turn_ledgers/*.jsonl (fönstrade med _day_key),
    tokens/ai_calls ur transkriptens dagböcker, tokens_per_sek/kr_per_1m_tokens
  - GET /api/admin/overview: window-validering (400), 403 icke-admin, grantad
    tier utan ledger-rad = 0 kr, kompakta användarrader (utan daily/model_tokens),
    fönstret rör BARA fönstrade nycklar
  - additiva nycklar i /api/admin/billing + /api/admin/user/{username}

Ingen riktig data rörs: autouse-fixtures pekar users.json (auth.USERS_FILE),
billing-ledgern + churn (main._LEDGER_FILE/_CHURN_FILE), kampanjmappen
(state_manager.CAMPAIGNS_DIR + main.CAMPAIGNS_DIR) och iplog-cachen mot tmp.
turn_ledgers pekas om av tests/conftest.py. Geo läses ur den MOCKADE cachen —
ingen nätverksväg och backend/data/ip_geo.json öppnas aldrig.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import iplog  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    """users.json → tmp. ALDRIG den riktiga filen (läckan 2026-08-04)."""
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    """Billing-ledgern + churn-ackumulatorn → tmp."""
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    monkeypatch.setattr(main, "_CHURN_FILE", tmp_path / "_churn.json")
    return f


@pytest.fixture(autouse=True)
def campaigns_dir(tmp_path, monkeypatch):
    """Kampanj-data → tmp (state_manager + main)."""
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def geo_cache(tmp_path, monkeypatch):
    """iplog i rent cache-läge: ingen ip_geo.json, ingen kö, inget nätverk.

    Testerna fyller cachen själva via _set_geo()/_set_geo_unknown().
    IP_GEO_FILE/VISITS_FILE pekas också mot tmp: main-middelwaren anropar
    record_ip()/record_visit() för varje request, och utan detta läcker
    (autentiserade) testanrop till de RIKTIGA backend/data-filerna.
    """
    monkeypatch.setattr(iplog, "IP_GEO_FILE", tmp_path / "ip_geo.json")
    monkeypatch.setattr(iplog, "VISITS_FILE", tmp_path / "visits.json")
    monkeypatch.setattr(iplog, "_loaded", True)
    monkeypatch.setattr(iplog, "_ip_store", {})
    monkeypatch.setattr(iplog, "_geo_cache", {})
    monkeypatch.setattr(iplog, "_geo_queue", set())
    monkeypatch.setattr(iplog, "_geo_inflight", set())
    monkeypatch.setattr(iplog, "_visits_loaded", True)
    monkeypatch.setattr(iplog, "_visit_store", {"total": 0, "by_day": {}, "by_ip": {},
                                                "by_referrer": {}, "by_day_unique": {}})
    return iplog._geo_cache


@pytest.fixture
def client(users_file, ledger_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── Hjälpare ─────────────────────────────────────────────────────────────

def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _ts(days_ago: int = 0) -> str:
    """UTC-ISO-tid `days_ago` dygn bakåt (transkript/ledger-format)."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _local_day(days_ago: int = 0) -> str:
    """Lokal dag (Europe/Stockholm) `days_ago` dygn bakåt."""
    return (datetime.now(main._LOCAL_TZ).date() - timedelta(days=days_ago)).isoformat()


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
        "reset_date": datetime.now(timezone.utc).date().isoformat(),
        "subscription_status": "free",
        "subscription_until": None,
        "features": {},
        "start_bonus_granted": True,
    })
    u.update(fields)
    main.save_users(users)


def _seed_ledger(rows: list[tuple]) -> None:
    """Skriv ledger-rader direkt till tmp-ledgern: (user, sek, type, ts)."""
    data = [{"ts": ts, "user": user, "amount_sek": sek, "type": rtype,
             "stripe_sub_id": None, "event_id": f"evt-{i}"}
            for i, (user, sek, rtype, ts) in enumerate(rows)]
    main._LEDGER_FILE.write_text(json.dumps(data), encoding="utf-8")


def _set_geo(username: str, ip: str, cc: str, country: str) -> None:
    """Fyll iplog-cachen för en användare (ingen nätverksväg finns i test)."""
    iplog._ip_store[username] = {"ip": ip, "first_seen": 1.0, "last_seen": 1.0}
    iplog._geo_cache[ip] = {"country": country, "countryCode": cc, "ts": 1.0}


def _set_geo_unknown(username: str, ip: str) -> None:
    """Användare med IP men UTAN cache-rad → landet är okänt ("??")."""
    iplog._ip_store[username] = {"ip": ip, "first_seen": 1.0, "last_seen": 1.0}
    iplog._geo_cache.pop(ip, None)


def _write_turn_ledger(username: str, rows: list) -> None:
    d = main._TURN_LEDGERS_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{username}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _atok() -> str:
    return create_token("the_admin", "admin")


def _ptok() -> str:
    return create_token("alice", "player")


def _fake_scan(model: str = "step-3.7-flash", tokens: int = 1_000_000, calls: int = 4,
               model_daily: dict | None = None):
    """Stand-in för _scan_user_transcripts med komplett nyckeluppsättning.

    model_daily = {model: {dag: anrop}} läggs till vid behov (samma form som
    den riktiga scannen lämnar — _model_breakdown läser den).
    """
    day = _local_day(0)
    def scan(user):
        return {
            "model_daily": json.loads(json.dumps(model_daily or {})),
            "prompt_tokens": tokens,
            "completion_tokens": 0,
            "total_tokens": tokens,
            "turns": 7,
            "last_active": _ts(0),
            "sessions": [],
            "tts_usage": {"calls": 0, "api_calls": 0, "chars": 0, "tokens": 0, "seconds": 0.0},
            "model_tokens": {model: {"prompt_tokens": tokens, "completion_tokens": 0, "calls": calls}},
            "daily": {day: {"calls": calls, "tokens": tokens}},
            "character_creation": {"tokens": 0, "calls": 0},
            "image_gen": {"calls": 0, "by_model": {}},
            "deleted_campaigns": {},
        }
    return scan


# ── _revenue_breakdown ───────────────────────────────────────────────────

def test_by_product_sums_to_ledger_total(ledger_file):
    _seed_admin()
    _seed_player("alice")
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", _ts(1)),
        ("bob", 70, "stripe:donation", _ts(2)),
        ("carol", 351, "stripe:patron500", _ts(3)),
        ("dave", 1170, "stripe:lifetime", _ts(4)),
    ])
    bd = main._revenue_breakdown()
    per_key = {p["key"]: p["sek"] for p in bd["by_product"]}
    assert per_key["unlock10"] == 117
    assert per_key["donation"] == 70
    assert per_key["patron500"] == 351
    assert per_key["lifetime"] == 1170
    assert sum(p["sek"] for p in bd["by_product"]) == main._ledger_totals()["total"] == 1708
    assert bd["paying_customers"] == 4
    # BY_KEY = ledger-typen utan "stripe:"-prefix, med label + count
    unlock = next(p for p in bd["by_product"] if p["key"] == "unlock10")
    assert set(unlock) == {"key", "label", "sek", "count"}
    assert unlock["count"] == 1 and unlock["label"]


def test_unknown_ledger_type_lands_in_other(ledger_file):
    _seed_ledger([
        ("alice", 42, "topup", _ts(1)),
        ("bob", 10, "mystery-thing", _ts(1)),
    ])
    bd = main._revenue_breakdown()
    keys = [p["key"] for p in bd["by_product"]]
    other = next(p for p in bd["by_product"] if p["key"] == "other")
    assert other["sek"] == 52 and other["count"] == 2
    assert "topup" not in keys and "mystery-thing" not in keys
    assert sum(p["sek"] for p in bd["by_product"]) == main._ledger_totals()["total"] == 52


def test_churn_and_cancel_rows_are_excluded(ledger_file):
    churn_day = _ts(2)
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", _ts(1)),
        ("nomis", 0, "stripe:churn", churn_day),
        ("nomis", 0, "stripe:cancel_scheduled", _ts(3)),
    ])
    bd = main._revenue_breakdown()
    keys = [p["key"] for p in bd["by_product"]]
    assert "churn" not in keys and "cancel_scheduled" not in keys
    # ingen intäktspåverkan + ingen spökdag i serierna
    assert sum(p["sek"] for p in bd["by_product"]) == main._ledger_totals()["total"] == 117
    assert main._day_key(churn_day) not in bd["by_date"]
    # nomis har inga intäktsrader kvar → räknas inte som betalare
    assert "nomis" not in [c["user"] for c in bd["customers"] if c["payments"] > 0]
    assert bd["paying_customers"] == 1


def test_live_products_listed_even_with_zero(ledger_file):
    bd = main._revenue_breakdown()
    keys = {p["key"]: p for p in bd["by_product"]}
    assert set(keys) == {"unlock10", "donation", "patron500", "lifetime"}
    for k in ("unlock10", "donation", "patron500", "lifetime"):
        assert keys[k]["sek"] == 0 and keys[k]["count"] == 0
    # legacy-nycklar utan rader visas INTE, "other" finns bara när den har rader
    assert "tier1" not in keys and "tier2" not in keys and "renewal" not in keys
    assert "other" not in keys
    assert bd["by_month"] == [] and bd["by_date"] == {} and bd["by_country"] == []
    assert bd["paying_customers"] == 0 and bd["first_ts"] is None and bd["last_ts"] is None


def test_by_month_and_by_date_bucket_in_stockholm_time(ledger_file):
    """23:30 UTC sista augusti = 01:30 lokal 1 september → NÄSTA månad."""
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", "2026-08-31T23:30:00+00:00"),
        ("bob", 70, "stripe:donation", "2026-07-01T12:00:00+00:00"),
    ])
    bd = main._revenue_breakdown()
    assert [m["key"] for m in bd["by_month"]] == ["2026-07", "2026-09"]
    sept = next(m for m in bd["by_month"] if m["key"] == "2026-09")
    assert sept == {"key": "2026-09", "sek": 117, "count": 1}
    assert list(bd["by_date"]) == ["2026-07-01", "2026-09-01"]
    assert bd["by_date"]["2026-09-01"] == 117
    # allt är ints (frontend formaterar, räknar aldrig själv)
    assert all(isinstance(m["sek"], int) for m in bd["by_month"])
    assert all(isinstance(v, int) for v in bd["by_date"].values())


def test_by_country_aggregates_paying_accounts(ledger_file):
    _seed_player("alice")
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", _ts(1)),
        ("bob", 70, "stripe:donation", _ts(1)),
        ("carol", 1170, "stripe:lifetime", _ts(2)),
        ("dave", 0, "stripe:patron500", _ts(2)),  # 0-rad = ingen betalning
    ])
    _set_geo("alice", "203.0.113.7", "SE", "Sweden")
    _set_geo("bob", "203.0.113.9", "SE", "Sweden")
    _set_geo_unknown("carol", "203.0.113.11")
    bd = main._revenue_breakdown()
    assert bd["by_country"] == [
        {"cc": "??", "country": "Unknown", "sek": 1170, "count": 1, "paying": 1,
         "users": ["carol"]},
        {"cc": "SE", "country": "Sweden", "sek": 187, "count": 2, "paying": 2,
         "users": ["alice", "bob"]},
    ]


def test_customers_sorted_by_sek_with_payments(ledger_file):
    first_day = _ts(4)
    last_day = _ts(1)
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", last_day),
        ("alice", 70, "stripe:donation", first_day),
        ("bob", 1170, "stripe:lifetime", _ts(3)),
    ])
    bd = main._revenue_breakdown()
    assert [c["user"] for c in bd["customers"]] == ["bob", "alice"]
    bob, alice = bd["customers"]
    assert bob["sek"] == 1170 and bob["payments"] == 1 and bob["products"] == ["lifetime"]
    assert alice["sek"] == 187 and alice["payments"] == 2
    assert alice["products"] == ["donation", "unlock10"]
    assert alice["first_ts"] == first_day and alice["last_ts"] == last_day
    assert bd["paying_customers"] == 2
    assert bd["first_ts"] == first_day and bd["last_ts"] == last_day


# ── GET /api/admin/overview ──────────────────────────────────────────────

def test_overview_rejects_invalid_window(client):
    _seed_admin()
    r = client.get("/api/admin/overview?window=1y", cookies={"morkrets_token": _atok()})
    assert r.status_code == 400
    for w in ("24h", "7d", "30d", "all"):
        assert client.get(f"/api/admin/overview?window={w}",
                          cookies={"morkrets_token": _atok()}).status_code == 200


def test_overview_403_non_admin(client):
    _seed_player()
    r = client.get("/api/admin/overview", cookies={"morkrets_token": _ptok()})
    assert r.status_code == 403


def test_overview_granted_tier_without_payment_is_zero(client):
    """Grantad tier (setTier) skriver inget till ledgern → 0 kr i dashboarden.

    Speglar test_mrr_ignores_admintier_without_payment i test_billing_admin.
    """
    _seed_admin()
    _seed_player("granted", subscription_status="tier2", subscription_until=_in_days(30))
    body = client.get("/api/admin/overview", cookies={"morkrets_token": _atok()}).json()
    assert body["revenue"]["mrr"] == 0
    assert body["revenue"]["total"] == 0
    assert body["revenue"]["paying_customers"] == 0
    assert body["revenue"]["customers"] == []
    # admin-kontot har ingen tier → räknas som free (tiers = alla konton)
    assert body["tiers"] == {"free": 1, "tier1": 0, "tier2": 1, "lifetime": 0}
    row = next(u for u in body["users"] if u["username"] == "granted")
    assert row["revenue"] == 0
    assert row["subscription_status"] == "tier2"


def test_overview_user_rows_are_compact(client):
    _seed_admin()
    _seed_player("alice")
    body = client.get("/api/admin/overview", cookies={"morkrets_token": _atok()}).json()
    # toppnivå-kontraktet
    assert set(body) == {"generated_at", "window", "totals", "revenue", "value",
                         "series", "usage", "traffic", "tiers", "users",
                         # Turn-pott (2026-09-28): free/paid-legend + pottsummor
                         "coding_summary", "pool_totals"}
    assert set(body["totals"]) == {"accounts", "players", "admins", "campaigns",
                                   "turns", "tokens", "ai_calls", "visits"}
    assert set(body["series"]) == {"api_calls_day", "visits_day", "visits_unique_day",
                                   "revenue_day", "signups_day", "turns_day"}
    assert set(body["usage"]) == {"providers", "models"}
    # traffic bär nu även unika besökare + referrer-detaljen (2026-09-27:
    # "samtliga traffic-referrals syns" + KPI:n fick riktiga unika)
    assert set(body["traffic"]) == {"by_country", "referrers", "referrer_detail",
                                    "uniques", "total", "today", "last_7", "window"}
    assert set(body["value"]) == {"turns", "tokens", "ai_calls", "tokens_per_sek",
                                  "kr_per_1m_tokens", "turns_windowed",
                                  "turns_day", "by_action",
                                  # per hink och dag (2026-09-28)
                                  "turns_by_bucket_day"}
    assert body["totals"]["accounts"] == 2 and body["totals"]["admins"] == 1
    assert body["totals"]["players"] == 1
    # kompakta rader: BARA tabellfälten — aldrig daily/model_tokens (159 konton)
    row = next(u for u in body["users"] if u["username"] == "alice")
    assert set(row) == set(main._OVERVIEW_USER_FIELDS)
    assert "daily" not in row and "model_tokens" not in row and "ip" not in row
    assert "country_flag" in row


def test_overview_exposes_turn_pool_coding_and_bucket_series(client):
    """Turn-pott (2026-09-28, rostad): kompakta pott-fält + free/paid-kod per
    rad, server-räknade summor, och en hink-serie som summerar mot turns_day.

    Kodningen är tre koder: `granted` får ALDRIG se ut som ett köp."""
    _seed_admin()
    _seed_player("frida")                       # ren gratispott → free
    _seed_player("gustav", turn_bonus=300)      # grant utan betalning → granted
    _seed_player("pelle", promo_bonus=300)      # legacy-promo → granted
    _seed_player("kalle")                       # betalningsrad → paid
    _seed_ledger([("kalle", 70, "stripe:donation", _ts(0))])
    _write_turn_ledger("frida", [
        {"ts": _ts(0), "action": "dm", "model": None, "tokens": 0, "bucket": "free"},
    ])
    _write_turn_ledger("gustav", [
        {"ts": _ts(0), "action": "dm", "model": None, "tokens": 0, "bucket": "paid"},
        # rad UTAN bucket (skriven före 2026-09-28) → "unknown", aldrig "free"
        {"ts": _ts(40), "action": "dm", "model": None, "tokens": 0},
    ])

    body = client.get("/api/admin/overview?window=all",
                      cookies={"morkrets_token": _atok()}).json()
    rows = {u["username"]: u for u in body["users"]}

    assert rows["frida"]["coding"]["code"] == "free"
    assert rows["gustav"]["coding"]["code"] == "granted"
    assert rows["gustav"]["coding"]["code"] != "paid"      # grant ≠ köp
    assert rows["pelle"]["coding"]["code"] == "granted"
    assert rows["kalle"]["coding"]["code"] == "paid"
    assert rows["kalle"]["coding"]["why"] == "70 kr paid"
    # Kompakt rad bär bara code/tier/why — flaggorna (paid/granted) hör till
    # dossiéns fulla coding-objekt, så payloaden inte växer i onödan.
    assert set(rows["gustav"]["coding"]) == {"code", "tier", "why"}

    # pott-fälten är server-räknade och säger "köpt: okänt" utan grant-rader
    assert rows["gustav"]["turn_pool"]["paid_left"] == 300
    assert rows["gustav"]["turn_pool"]["paid_granted"] == 0
    assert rows["gustav"]["turn_pool"]["paid_granted_known"] is False
    assert rows["frida"]["turn_pool"]["free_cap"] == main.DEFAULT_TURN_CAP

    # legenden: bara riktiga koder, summan = antalet konton.
    # the_admin har cap 0 = oändlig pott → "granted" (inte gratiskvoten, inte
    # betalande) — personal-konton skiljs ut med Role-filtret i dashboarden.
    assert set(body["coding_summary"]) == {"paid", "granted", "free"}
    assert sum(body["coding_summary"].values()) == body["totals"]["accounts"]
    assert body["coding_summary"] == {"paid": 1, "granted": 3, "free": 1}
    assert rows["the_admin"]["turn_pool"]["unlimited"] is True

    # hink-serien summerar exakt mot turns_day (samma scan, samma fönster)
    bd = body["value"]["turns_by_bucket_day"]
    td = body["value"]["turns_day"]
    assert set(bd) == set(td)
    for day, split in bd.items():
        assert sum(split.values()) == td[day], day
    assert bd[_local_day(0)]["free"] == 1
    assert bd[_local_day(0)]["paid"] == 1
    assert bd[_local_day(40)]["unknown"] == 1

    # pottsummorna räknas server-side (UI:t ska inte summera själv)
    assert body["pool_totals"]["paid_left"] == 300
    assert body["pool_totals"]["free_left"] >= main.DEFAULT_TURN_CAP


def test_overview_window_filters_only_windowed_series(client):
    _seed_admin()
    _seed_player("alice")
    recent, old = _ts(0), _ts(40)
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", recent),
        ("alice", 70, "stripe:donation", old),
    ])
    body_all = client.get("/api/admin/overview?window=all",
                          cookies={"morkrets_token": _atok()}).json()
    body_30 = client.get("/api/admin/overview?window=30d",
                         cookies={"morkrets_token": _atok()}).json()
    # livstidssiffrorna är IDENTISKA oavsett fönster (engångsköp-modellen)
    assert body_all["window"] == "all" and body_30["window"] == "30d"
    assert body_all["revenue"]["total"] == body_30["revenue"]["total"] == 187
    assert body_all["totals"] == body_30["totals"]
    # serien är fönstrad: gamla raden faller bort i 30d
    assert set(body_all["series"]["revenue_day"]) == {main._day_key(recent), main._day_key(old)}
    assert set(body_30["series"]["revenue_day"]) == {main._day_key(recent)}
    assert body_30["series"]["revenue_day"][main._day_key(recent)] == 117


# ── _value_delivered ─────────────────────────────────────────────────────

def test_value_delivered_counts_turns_from_turn_ledger(ledger_file):
    _seed_admin()
    _seed_player("alice")
    _write_turn_ledger("alice", [
        {"ts": _ts(0), "action": "chat", "model": "step-3.7-flash", "tokens": 10},
        {"ts": _ts(1), "action": "chat", "model": "step-3.7-flash", "tokens": 10},
        {"ts": _ts(40), "action": "chat", "model": "step-3.7-flash", "tokens": 10},
    ])
    _write_turn_ledger("bob", [{"ts": _ts(0), "action": "image", "model": "wan2.7-image", "tokens": 0}])
    v_all = main._value_delivered("all")
    assert v_all["turns"] == 4 and v_all["turns_windowed"] is True
    assert main._value_delivered("30d")["turns"] == 3     # alice 40 dagar bakåt faller bort
    assert main._value_delivered("7d")["turns"] == 3
    # en rad UTAN tidsstämpel kan inte fönstras: räknas bara i "all"
    _write_turn_ledger("carol", [{"action": "chat"}])
    assert main._value_delivered("all")["turns"] == 5
    assert main._value_delivered("all")["turns_windowed"] is False
    assert main._value_delivered("7d")["turns"] == 3
    assert main._value_delivered("7d")["turns_windowed"] is False


def test_value_delivered_tokens_from_daily_books(ledger_file, monkeypatch):
    _seed_admin()
    _seed_player("alice")
    _seed_ledger([("alice", 117, "stripe:unlock10", _ts(0))])
    today, old = _local_day(0), _local_day(40)

    def fake_scan(user):
        if user != "alice":
            return {"total_tokens": 0, "daily": {}}
        return {"total_tokens": 1_170_000, "daily": {today: {"calls": 3, "tokens": 1000},
                                                     old: {"calls": 5, "tokens": 2000}}}
    monkeypatch.setattr(main, "_scan_user_transcripts", fake_scan)
    v_all = main._value_delivered("all")
    v_30 = main._value_delivered("30d")
    assert v_all["tokens"] == 3000 and v_all["ai_calls"] == 8
    assert v_30["tokens"] == 1000 and v_30["ai_calls"] == 3
    # livstids-kvoterna (oberoende av fönstret): 1 170 000 tokens / 117 kr
    assert v_all["tokens_per_sek"] == 10000.0
    assert v_all["kr_per_1m_tokens"] == 100.0
    assert v_30["tokens_per_sek"] == 10000.0


def test_value_delivered_ratios_are_none_when_denominator_zero(ledger_file, monkeypatch):
    _seed_admin()
    monkeypatch.setattr(main, "_scan_user_transcripts",
                        lambda u: {"total_tokens": 500, "daily": {}})
    v = main._value_delivered("all")
    assert v["tokens_per_sek"] is None          # ingen intäkt → ingen kvot
    assert v["kr_per_1m_tokens"] == 0.0         # tokens>0 men 0 SEK
    _seed_ledger([("alice", 117, "stripe:unlock10", _ts(0))])
    monkeypatch.setattr(main, "_scan_user_transcripts",
                        lambda u: {"total_tokens": 0, "daily": {}})
    v = main._value_delivered("all")
    assert v["tokens_per_sek"] == 0.0
    assert v["kr_per_1m_tokens"] is None        # inga tokens → ingen kvot


def test_overview_value_and_usage_come_from_scan(client, monkeypatch):
    _seed_admin()
    _seed_player("alice")
    monkeypatch.setattr(main, "_scan_user_transcripts", _fake_scan())
    body = client.get("/api/admin/overview", cookies={"morkrets_token": _atok()}).json()
    assert body["totals"]["tokens"] == 2_000_000       # 2 konton × 1 000 000
    assert body["usage"]["providers"]["stepfun"]["tokens"] == 2_000_000
    assert body["usage"]["models"]["step-3.7-flash"]["calls"] == 8
    assert body["value"]["tokens"] == 2_000_000 and body["value"]["ai_calls"] == 8
    assert body["series"]["api_calls_day"][_local_day(0)] == 8
    assert body["window"] == "all"


# ── Additiva nycklar i billing + user-detail ─────────────────────────────

def test_billing_and_user_detail_add_breakdown_keys(client, ledger_file):
    _seed_admin()
    _seed_player("alice")
    _set_geo("alice", "203.0.113.7", "SE", "Sweden")
    _seed_ledger([
        ("alice", 117, "stripe:unlock10", _ts(1)),
        ("alice", 70, "stripe:donation", _ts(3)),
    ])
    billing = client.get("/api/admin/billing", cookies={"morkrets_token": _atok()}).json()
    # befintliga nycklar oförändrade
    assert billing["total"] == 187 and billing["transactions"] == 2
    assert billing["per_user"] == {"alice": 187} and billing["mrr"] == 0
    # nya nycklar
    assert billing["by_country"] == [{"cc": "SE", "country": "Sweden", "sek": 187,
                                      "count": 2, "paying": 1, "users": ["alice"]}]
    assert billing["paying_customers"] == 1
    assert billing["customers"][0]["payments"] == 2
    assert {p["key"] for p in billing["by_product"]} >= {"unlock10", "donation"}
    assert sum(p["sek"] for p in billing["by_product"]) == billing["total"]
    assert len(billing["by_month"]) == 1 and sum(v for v in billing["by_date"].values()) == 187

    detail = client.get("/api/admin/user/alice",
                        cookies={"morkrets_token": _atok()}).json()
    assert [r["amount_sek"] for r in detail["revenue_history"]] == [117, 70]  # nyaste först
    assert detail["revenue"] == 187
    assert isinstance(detail["daily"], dict) and isinstance(detail["model_mix"], dict)


def test_value_series_sum_to_the_kpi(ledger_file):
    """turns_day + by_action är drill-down av SAMMA scan → de måste summera
    exakt mot value["turns"] (annars är staplarna och KPI:n olika sanningar)."""
    turn_dir = main._TURN_LEDGERS_DIR
    turn_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(9):
        rows.append(json.dumps({"ts": _ts(i % 3), "action": "dm", "model": "m", "tokens": 10}))
    for i in range(4):
        rows.append(json.dumps({"ts": _ts(i % 2), "action": "guardian_pre", "model": "m", "tokens": 5}))
    (turn_dir / "alice.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    value = main._value_delivered("all")
    assert value["turns"] == 13
    assert sum(value["turns_day"].values()) == value["turns"]
    assert sum(value["by_action"].values()) == value["turns"]
    assert value["by_action"]["dm"] == 9 and value["by_action"]["guardian_pre"] == 4
    assert list(value["turns_day"]) == sorted(value["turns_day"])  # ascending för grafen

    windowed = main._value_delivered("24h")
    assert sum(windowed["turns_day"].values()) == windowed["turns"]
    assert sum(windowed["by_action"].values()) == windowed["turns"]


# ══ Drilldown-passet 2026-09-27 (rostad: "samtliga referrals", "modellanrop
#    per spelare", "drilldowns"). Backend-kontraktet för de nya vyerna. ═══════

def _seed_visits(referrers: dict, ips: dict, by_day: dict | None = None) -> None:
    """Fyll iplog:s besöksstore direkt (ingen nätverksväg i test).

    referrers = {källa: {ip: last_seen}}, ips = {ip: {countryCode, country, ts}}.
    """
    iplog._visit_store["by_referrer"] = {k: dict(v) for k, v in referrers.items()}
    last = {i: 1.0 for v in referrers.values() for i in v}
    for v in referrers.values():
        for ip, ts in v.items():
            last[ip] = max(last[ip], float(ts))
    iplog._visit_store["by_ip"] = {ip: {"first_seen": ts, "last_seen": ts, "hits": 1}
                                   for ip, ts in last.items()}
    iplog._visit_store["total"] = sum(len(v) for v in referrers.values())
    _seed_geo(ips)
    if by_day:
        iplog._visit_store["by_day"] = dict(by_day)


def _seed_geo(ips: dict) -> None:
    for ip, rec in ips.items():
        iplog._geo_cache[ip] = dict(rec)


def test_referrer_detail_lists_every_source_never_capped(ledger_file):
    """24 källor i storen → 24 rader ut. Klippningen satt i UI:t (slice(0, 8)),
    men detaljen måste bära ALLA källor, annars går de inte att visa alls."""
    now = time.time()
    srcs = ["Direct", "Reddit", "Google", "Bing", "DuckDuckGo", "chatgpt.com",
            "rostadexe.itch.io", "producthunt.com", "LinkedIn", "github.com",
            "rollspel.nu", "checkout.stripe.com", "com.reddit.frontpage",
            "old.reddit.com", "lt.reddit.com", "en.reddit.com", "is.reddit.com",
            "baidu.com", "Yandex", "dk.search.yahoo.com", "com.google.android.gm",
            "m.facebook.com", "beta.kblip.com", "txt.rostad.cc"]
    referrers = {s: {f"203.0.113.{i + 1}": now - i * 60} for i, s in enumerate(srcs)}
    ips = {f"203.0.113.{i + 1}": {"countryCode": "SE" if i % 2 else "US",
                                  "country": "Sweden" if i % 2 else "United States",
                                  "ts": now} for i in range(len(srcs))}
    _seed_visits(referrers, ips)

    detail = iplog.referrer_detail("all")
    assert len(detail) == len(srcs)                       # ingen 8-kapning
    assert set(detail) == set(srcs)
    google = detail["Google"]
    assert google["uniques"] == 1
    assert google["countries"] == {ips[referrers["Google"].popitem()[0]]["countryCode"]: 1}  # ur cachen
    assert google["first_seen"] > 0 and google["last_seen"] > 0
    assert google["last_seen"] >= google["first_seen"]
    assert not google.get("legacy")

    # sammanfattningen (by_referrer) är fortfarande en ren räknare per källa
    summary = asyncio.run(iplog.visits_summary())
    assert len(summary["by_referrer"]) == len(srcs)


def test_referrer_detail_windows_on_last_visit_from_the_source(ledger_file):
    """Fönstret filtrerar på IP:ets SENASTE besök från källan — samma regel som
    land-grafen (_range_cutoff), annars skulle de två graferna visa olika tal."""
    now = time.time()
    _seed_visits(
        {"Reddit": {"198.51.100.1": now - 3600,          # färsk
                    "198.51.100.2": now - 40 * 86400},   # gammal
         "Google": {"198.51.100.3": now - 2 * 86400}},   # 2 dygn gammal
        {"198.51.100.1": {"countryCode": "SE", "country": "Sweden", "ts": now},
         "198.51.100.2": {"countryCode": "DE", "country": "Germany", "ts": now},
         "198.51.100.3": {"countryCode": "US", "country": "United States", "ts": now}})

    all_time = iplog.referrer_detail("all")
    assert all_time["Reddit"]["uniques"] == 2
    assert set(all_time["Reddit"]["countries"]) == {"SE", "DE"}
    day = iplog.referrer_detail("24h")
    assert day["Reddit"]["uniques"] == 1                  # bara den färska IP:n
    assert day["Reddit"]["countries"] == {"SE": 1}
    week = iplog.referrer_detail("7d")
    assert set(week) == {"Reddit", "Google"}              # båda har aktivitet < 7d
    assert week["Google"]["uniques"] == 1
    assert iplog.referrer_detail("1h")["Google"]["uniques"] == 0 or "Google" not in iplog.referrer_detail("1h")


def test_referrer_detail_legacy_counter_without_ips_is_honest(ledger_file):
    """Gammal store (int i stället för {ip: ts}) får INTE hitta på ett land."""
    _seed_visits({"OldSource": {"198.51.100.9": 1.0}}, {})
    iplog._visit_store["by_referrer"]["LegacyInt"] = 42
    detail = iplog.referrer_detail("all")
    assert detail["LegacyInt"]["uniques"] == 42
    assert detail["LegacyInt"]["countries"] == {}
    assert detail["LegacyInt"]["legacy"] is True


def test_visits_summary_days_parameter_carries_the_whole_history(ledger_file):
    """`days` styr hur många dagar by_day får innehålla. Admin begär 400 för
    "all" — annars visade grafen 14 staplar med etiketten "all" (lögn i UI)."""
    by_day = {_local_day(i): 10 + i for i in range(30)}
    _seed_visits({"Direct": {"198.51.100.1": time.time()}},
                 {"198.51.100.1": {"countryCode": "SE", "country": "Sweden", "ts": time.time()}},
                 by_day=by_day)
    default = asyncio.run(iplog.visits_summary())
    assert len(default["by_day"]) == 14                   # bakåtkompatibelt default
    full = asyncio.run(iplog.visits_summary(days=400))
    assert set(full["by_day"]) == set(by_day)
    assert full["by_day"][_local_day(29)] == 39


def test_visits_summary_reports_unique_visitors_not_requests(ledger_file):
    """KPI:n "Unique visitors" måste vara distinkta IP:er — inte request-summan.
    (Dashboarden visade tidigare 14 849 requests som "unika besökare".)"""
    now = time.time()
    _seed_visits({"Direct": {"198.51.100.1": now, "198.51.100.2": now - 2 * 86400},
                  "Google": {"198.51.100.3": now}},
                 {"198.51.100.1": {"countryCode": "SE", "country": "Sweden", "ts": now},
                  "198.51.100.2": {"countryCode": "DE", "country": "Germany", "ts": now},
                  "198.51.100.3": {"countryCode": "US", "country": "United States", "ts": now}},
                 by_day={_local_day(0): 500, _local_day(1): 400})
    s = asyncio.run(iplog.visits_summary())
    assert s["by_day"][_local_day(0)] == 500               # requests
    assert s["uniques"]["total"] == 3                      # IP:n, inte 900
    assert s["uniques"]["last_7"] == 3
    assert s["total"] == 3                                 # seedad store-total


# ── /api/admin/overview: de nya traffic-fälten ───────────────────────────

def test_overview_traffic_carries_referrer_detail_and_uniques(client, ledger_file):
    _seed_admin()
    _seed_player("alice")
    now = time.time()
    _seed_visits({f"src{i}": {f"198.51.100.{i}": now} for i in range(12)},
                 {f"198.51.100.{i}": {"countryCode": "SE", "country": "Sweden", "ts": now}
                  for i in range(12)})
    body = client.get("/api/admin/overview?window=all",
                      cookies={"morkrets_token": _atok()}).json()
    t = body["traffic"]
    assert t["window"] == "all"
    assert len(t["referrer_detail"]) >= 12                 # aldrig kapad
    assert t["uniques"]["total"] >= 12
    assert t["total"] >= 12 and "today" in t and "last_7" in t
    # land-grafen fönstras av samma regel som detaljen
    w = client.get("/api/admin/overview?window=24h",
                   cookies={"morkrets_token": _atok()}).json()
    assert set(t["referrer_detail"]) == set(w["traffic"]["referrer_detail"])


def test_visits_country_route_windows_and_requires_admin(client, ledger_file):
    import asyncio
    _seed_admin()
    _seed_player("alice")
    now = time.time()
    _seed_visits({"Direct": {"198.51.100.1": now, "198.51.100.2": now - 40 * 86400}},
                 {"198.51.100.1": {"countryCode": "SE", "country": "Sweden", "ts": now},
                  "198.51.100.2": {"countryCode": "DE", "country": "Germany", "ts": now}})
    ok = client.get("/api/admin/visits_country?window=24h",
                    cookies={"morkrets_token": _atok()})
    assert ok.status_code == 200
    assert ok.json()["by_country"] == {"SE": 1}            # gamla DE-IP:n utanför
    assert client.get("/api/admin/visits_country?window=all",
                      cookies={"morkrets_token": _atok()}).json()["by_country"] == {"SE": 1, "DE": 1}
    assert client.get("/api/admin/visits_country?window=24h",
                      cookies={"morkrets_token": _ptok()}).status_code == 403
    assert asyncio.run(iplog.visits_summary())["uniques"]["total"] == 2


# ── /api/admin/model/{model}: "modellanrop per spelare" ──────────────────

def test_model_detail_returns_curve_and_players(client, monkeypatch):
    _seed_admin()
    _seed_player("alice")
    _seed_player("bob")
    day = _local_day(0)
    old = _local_day(40)

    def scan(user):
        if user == "alice":
            return _fake_scan("qwen3.8-max", tokens=900, calls=3,
                              model_daily={"qwen3.8-max": {day: 3, old: 5}})(user)
        if user == "bob":
            return _fake_scan("qwen3.8-max", tokens=100, calls=1,
                              model_daily={"qwen3.8-max": {day: 1}})(user)
        return _fake_scan("other-model", tokens=10, calls=1)(user)
    monkeypatch.setattr(main, "_scan_user_transcripts", scan)

    body = client.get("/api/admin/model/qwen3.8-max?window=30d",
                      cookies={"morkrets_token": _atok()}).json()
    assert body["model"] == "qwen3.8-max"
    assert body["calls"] == 4 and body["tokens"] == 1000   # livstid
    assert body["calls_window"] == 4                       # gamla dagen utanför 30d
    assert body["windowed"] is True and body["has_day_series"] is True
    assert body["day"] == {day: 4}                         # kurvan, sorterad
    assert [u["username"] for u in body["users"]] == ["alice", "bob"]  # flest anrop först
    # qwen3.8-max är pinnad för tunga körningar och står INTE i MODELS — men
    # providern kan attribueras, så modellen är känd (buggen: known=False här).
    assert body["registered"] is False and body["known"] is True
    alice = body["users"][0]
    assert alice["calls"] == 3 and alice["calls_window"] == 3 and alice["tokens"] == 900
    assert alice["subscription_status"] == "free" and "player" == alice["role"]
    # modellen finns i registret
    assert body["known"] is True
    # fönstret all → hela kurvan
    allw = client.get("/api/admin/model/qwen3.8-max?window=all",
                      cookies={"morkrets_token": _atok()}).json()
    assert allw["day"] == {day: 4, old: 5}
    assert allw["calls_window"] == 9
    assert allw["users"][0]["calls_window"] == 8           # alice 3 + 5


def test_model_detail_unknown_model_is_empty_not_an_error(client):
    _seed_admin()
    r = client.get("/api/admin/model/no-such-model-xyz",
                   cookies={"morkrets_token": _atok()})
    assert r.status_code == 200
    body = r.json()
    assert body["known"] is False and body["registered"] is False and body["media"] is False
    assert body["users"] == [] and body["calls"] == 0 and body["day"] == {}


def test_model_detail_flags_registry_membership_honestly(client):
    """`registered` (i MODELS) och `media` (state-räknad TTS/bild) är egna
    flaggor — UI:t ska kunna skilja "aktiv modell" från "pinnad/historisk"."""
    _seed_admin()
    _seed_player("alice")
    reg = client.get("/api/admin/model/step-3.7-flash",
                     cookies={"morkrets_token": _atok()}).json()
    assert reg["registered"] is True and reg["media"] is False and reg["known"] is True
    med = client.get("/api/admin/model/stepaudio-2.5-tts",
                     cookies={"morkrets_token": _atok()}).json()
    assert med["media"] is True and med["registered"] is False and med["known"] is True


def test_model_detail_media_model_is_not_claimed_to_be_windowed(client, monkeypatch):
    """TTS-/bildmodeller har ingen dagserie i datat → windowed=False, annars
    påstår UI:t ett fönster som underlaget inte har."""
    _seed_admin()
    _seed_player("alice")

    def scan(user):
        base = _fake_scan("step-3.7-flash", tokens=0, calls=0)(user)
        if user == "alice":
            base["tts_usage"] = {"calls": 4, "api_calls": 4, "chars": 120, "tokens": 0,
                                 "seconds": 1.0, "by_model": {"stepaudio-2.5-tts": 4}}
        return base
    monkeypatch.setattr(main, "_scan_user_transcripts", scan)

    body = client.get("/api/admin/model/stepaudio-2.5-tts?window=24h",
                      cookies={"morkrets_token": _atok()}).json()
    assert body["media_calls"] == 4
    assert body["has_day_series"] is False
    assert body["windowed"] is False
    assert body["known"] is True
    assert body["users"][0]["media_calls"] == 4


def test_model_detail_rejects_bad_window_and_non_admin(client):
    _seed_admin()
    _seed_player("alice")
    assert client.get("/api/admin/model/step-3.7-flash?window=6h",
                      cookies={"morkrets_token": _atok()}).status_code in (400, 422)
    assert client.get("/api/admin/model/step-3.7-flash",
                      cookies={"morkrets_token": _ptok()}).status_code == 403
    assert client.get("/api/admin/model/step-3.7-flash").status_code in (401, 403)
