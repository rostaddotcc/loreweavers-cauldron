"""2026-08-05: besöksräkning (admin-vyn).

Rostad: "Antal besök, besök per land och så?" — middleware räknar sidvisningar
(HTML-sidor, ej API) → iplog.record_visit → data/visits.json. Admin-stats
exponerar `visits`: {total, today, last_7, by_day, by_country}.

Ingen riktig data rörs: users.json, ip_geo.json och visits.json pekas om till
tmp; geo-cachen seedas så inget nätverksanrop görs.
"""

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
import iplog  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def campaigns_dir(tmp_path, monkeypatch):
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def visits_file(tmp_path, monkeypatch):
    f = tmp_path / "visits.json"
    monkeypatch.setattr(iplog, "VISITS_FILE", f)
    monkeypatch.setattr(iplog, "_visits_loaded", False)
    monkeypatch.setattr(iplog, "_visit_store", {"total": 0, "by_day": {}, "by_ip": {}})
    return f


@pytest.fixture(autouse=True)
def ip_store(tmp_path, monkeypatch):
    f = tmp_path / "ip_geo.json"
    monkeypatch.setattr(iplog, "IP_GEO_FILE", f)
    monkeypatch.setattr(iplog, "_loaded", False)
    monkeypatch.setattr(iplog, "_ip_store", {})
    return f


@pytest.fixture
def client(users_file, campaigns_dir, visits_file, ip_store):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── record_visit ─────────────────────────────────────────────────────────

def test_record_visit_increments(visits_file):
    iplog.record_visit("1.2.3.4")
    iplog.record_visit("1.2.3.4")
    iplog.record_visit("9.9.9.9")
    today = time.strftime("%Y-%m-%d")
    assert iplog._visit_store["total"] == 3
    assert iplog._visit_store["by_day"][today] == 3
    assert iplog._visit_store["by_ip"]["1.2.3.4"]["count"] == 2
    assert iplog._visit_store["by_ip"]["9.9.9.9"]["count"] == 1
    # Persistens: ladda om från disk
    iplog._visits_loaded = False
    iplog._visit_store = {"total": 0, "by_day": {}, "by_ip": {}}
    iplog.record_visit("1.2.3.4")
    assert iplog._visit_store["total"] == 4


def test_legacy_int_ip_format_migrated(visits_file):
    iplog._visit_store["by_ip"]["1.2.3.4"] = 5  # gammalt format (int)
    iplog.record_visit("1.2.3.4")
    assert iplog._visit_store["by_ip"]["1.2.3.4"]["count"] == 6


def test_by_day_pruned_to_32_days(visits_file):
    now = time.time()
    for i in range(40):
        d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
        iplog._visit_store["by_day"][d] = 1
    iplog.record_visit("1.2.3.4")  # triggar trim
    assert len(iplog._visit_store["by_day"]) <= 32


# ── visits_summary ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_visits_summary_country_aggregation(visits_file):
    iplog.record_visit("1.2.3.4")   # SE
    iplog.record_visit("1.2.3.4")   # SE
    iplog.record_visit("9.9.9.9")   # DE
    iplog.record_visit("192.168.1.5")  # LOCAL
    # Seed geo-cache så ingen nätverksuppslagning sker
    now = time.time()
    iplog._geo_cache["1.2.3.4"] = {"country": "Sweden", "countryCode": "SE", "ts": now}
    iplog._geo_cache["9.9.9.9"] = {"country": "Germany", "countryCode": "DE", "ts": now}
    s = await iplog.visits_summary()
    assert s["total"] == 4
    assert s["by_country"]["SE"] == 2
    assert s["by_country"]["DE"] == 1
    assert s["by_country"]["LOCAL"] == 1
    assert s["last_7"] >= 4
    assert s["today"] >= 4
    # Unique-besök: 3 distinkta IP:er (1.2.3.4, 9.9.9.9, 192.168.1.5)
    assert s["unique_total"] == 3
    assert s["unique_today"] == 3
    assert s["unique_7d"] == 3


# ── Admin-stats ──────────────────────────────────────────────────────────

def test_admin_stats_includes_visits(client, visits_file):
    main.save_users({
        "the_admin": {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0},
    })
    iplog.record_visit("1.2.3.4")
    iplog.record_visit("1.2.3.4")
    now = time.time()
    iplog._geo_cache["1.2.3.4"] = {"country": "Sweden", "countryCode": "SE", "ts": now}
    atok = create_token("the_admin", "admin")
    r = client.get("/api/admin/stats", cookies={"morkrets_token": atok})
    assert r.status_code == 200, r.text
    visits = r.json()["visits"]
    assert visits["total"] == 2
    assert visits["by_country"]["SE"] == 2
    assert visits["today"] >= 2
    assert visits["unique_total"] == 1


def test_middleware_counts_page_views(client, visits_file):
    """HTML-sidor räknas som besök; API-anrop gör det inte."""
    r = client.get("/login.html")
    assert r.status_code == 200
    r2 = client.get("/pricing.html")
    assert r2.status_code == 200
    r3 = client.get("/api/me")  # ej inloggad → 401, men ska INTE räknas
    assert r3.status_code == 401
    assert iplog._visit_store["total"] == 2
