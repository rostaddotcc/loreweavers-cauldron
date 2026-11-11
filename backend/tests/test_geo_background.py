"""Bakgrunds-geo (2026-09-20, rostad: "sluta pinga hela dagarna").

Kontrakt:
- Admin-ytor (visits_summary, geo_for_users, geo_for_ip) gör ALDRIG
  blockande nätverksanrop — de läser cachen och köar bakgrundsuppslag.
- Stale cache visas hellre än "??" (länder flyttar inte).
- Daglig budget + negativ cache (fail) + kö-dedup.
- record_ip köar vid NY/ÄNDRAD IP; record_visit köar endast okända IP:er.

Ingen riktig data rörs: iplog-filer pekas om till tmp, _geo_fetch monkey-
patchas till en fake (räknar anrop, inget nätverk).
"""

import asyncio
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import iplog  # noqa: E402


@pytest.fixture(autouse=True)
def iso_geo(tmp_path, monkeypatch):
    """Full isolering av ALL geo-state (filer + in-memory + budget + kö)."""
    monkeypatch.setattr(iplog, "IP_GEO_FILE", tmp_path / "ip_geo.json")
    monkeypatch.setattr(iplog, "VISITS_FILE", tmp_path / "visits.json")
    monkeypatch.setattr(iplog, "_loaded", False)
    monkeypatch.setattr(iplog, "_visits_loaded", False)
    monkeypatch.setattr(iplog, "_ip_store", {})
    monkeypatch.setattr(iplog, "_geo_cache", {})
    monkeypatch.setattr(iplog, "_visit_store",
                        {"total": 0, "by_day": {}, "by_ip": {}, "by_referrer": {}, "by_day_unique": {}})
    monkeypatch.setattr(iplog, "_geo_queue", set())
    monkeypatch.setattr(iplog, "_geo_inflight", set())
    monkeypatch.setattr(iplog, "_geo_worker", None)
    monkeypatch.setattr(iplog, "_budget_day", "")
    monkeypatch.setattr(iplog, "_budget_used", 0)
    return tmp_path


@pytest.fixture(autouse=True)
def restore_default_event_loop():
    """pytest-asyncio river main-threadens default-loop i teardown — men
    SENARE testfiler (test_guardian_spell_slots) använder den deprecateda
    asyncio.get_event_loop()-policyn och kräver att den finns. Utan detta
    läcker denna fil "no current event loop in thread 'MainThread'" till dem.
    """
    yield
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _fake_fetch_factory(monkeypatch, code="SE", fail=False):
    """Ersätt _geo_fetch med en fake som räknar anrop — ALDRIG nätverk."""
    calls = []

    async def fake(ip, sem):
        calls.append(ip)
        await asyncio.sleep(0)
        if fail:
            iplog._geo_cache[ip] = {"country": "", "countryCode": "", "ts": time.time(), "fail": True}
        else:
            iplog._geo_cache[ip] = {"country": "Testland", "countryCode": code, "ts": time.time()}
        return iplog.geo_cached(ip)

    monkeypatch.setattr(iplog, "_geo_fetch", fake)
    return calls


async def _drain():
    """Kör workern tills kön är tom (test-hjälp)."""
    iplog._ensure_geo_worker()
    for _ in range(50):
        if not iplog._geo_queue and not iplog._geo_inflight:
            break
        await asyncio.sleep(0.02)


# ── Kontrakt 1: admin-ytor gör aldrig nätverk ───────────────────────────

@pytest.mark.asyncio
async def test_visits_summary_never_calls_network_inline(iso_geo, monkeypatch):
    """Okänd IP i by_ip → visas som '??' direkt, köas till bakgrunden.
    Ett inline-nätverksanrop hade gett landet direkt — det får inte hända."""

    async def forbidden(ip):  # gammal geo_for_ip-signatur som gjorde inline-uppslag
        raise AssertionError("visits_summary får inte slå upp inline")

    monkeypatch.setattr(iplog, "geo_for_ip", forbidden)
    iplog._visit_store["by_ip"]["4.5.6.7"] = {"count": 3, "last_seen": time.time()}
    s = await iplog.visits_summary()
    assert s["by_country"] == {"??": 1}
    assert "4.5.6.7" in iplog._geo_queue  # köad, inte uppslagen


@pytest.mark.asyncio
async def test_geo_for_users_reads_cache_only(iso_geo, monkeypatch):
    calls = _fake_fetch_factory(monkeypatch)
    iplog.record_ip("p1", "1.1.1.1")   # köar (ingen worker i sync-kontext)
    iplog.record_ip("p2", "192.168.0.5")  # privat → köas aldrig
    result = await iplog.geo_for_users({"p1": {}, "p2": {}})
    # FÖRE worker-dränering: p1 har ingen cache → tom sträng, inte uppslagen inline
    assert result["p1"]["countryCode"] == ""
    assert result["p2"]["countryCode"] == "LOCAL"
    assert calls == []  # inget fetch anropat än


@pytest.mark.asyncio
async def test_geo_for_ip_returns_cache_and_queues(iso_geo, monkeypatch):
    calls = _fake_fetch_factory(monkeypatch)
    r = await iplog.geo_for_ip("8.8.8.8")
    assert r == {"country": "", "countryCode": ""}  # cache-först
    assert "8.8.8.8" in iplog._geo_queue
    await _drain()
    assert calls == ["8.8.8.8"]
    assert iplog.geo_cached("8.8.8.8")["countryCode"] == "SE"


# ── Kontrakt 2: stale cache visas hellre än tomt ────────────────────────

@pytest.mark.asyncio
async def test_stale_cache_still_displayed(iso_geo):
    old = time.time() - 400 * 86400  # 400 dagar gammal
    iplog._geo_cache["2.2.2.2"] = {"country": "Sweden", "countryCode": "SE", "ts": old}
    iplog._visit_store["by_ip"]["2.2.2.2"] = {"count": 1, "last_seen": time.time()}
    s = await iplog.visits_summary()
    assert s["by_country"]["SE"] == 1  # inte "??" trots TTL passerad


@pytest.mark.asyncio
async def test_stale_cache_queued_for_background_refresh(iso_geo, monkeypatch):
    calls = _fake_fetch_factory(monkeypatch, code="NO")
    old = time.time() - (iplog.GEO_REFRESH_AGE + 100)
    iplog._geo_cache["3.3.3.3"] = {"country": "Sweden", "countryCode": "SE", "ts": old}
    r = await iplog.geo_for_ip("3.3.3.3")
    assert r["countryCode"] == "SE"  # gammalt värde visas direkt
    await _drain()
    assert calls == ["3.3.3.3"]
    assert iplog.geo_cached("3.3.3.3")["countryCode"] == "NO"  # refreshad i bakgrunden


# ── Kontrakt 3: negativ cache (fail) ────────────────────────────────────

def test_failed_lookup_not_requeued_within_ttl(iso_geo):
    iplog._geo_cache["5.5.5.5"] = {
        "country": "", "countryCode": "", "ts": time.time() - 3600, "fail": True}
    iplog.queue_geo_lookup("5.5.5.5")
    assert "5.5.5.5" not in iplog._geo_queue  # fail <24 h → ingen retry
    # …men efter GEO_FAIL_TTL provas den igen
    iplog._geo_cache["5.5.5.5"]["ts"] = time.time() - iplog.GEO_FAIL_TTL - 10
    iplog.queue_geo_lookup("5.5.5.5")
    assert "5.5.5.5" in iplog._geo_queue


# ── Kontrakt 4: budget ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_budget_stops_worker(iso_geo, monkeypatch):
    calls = _fake_fetch_factory(monkeypatch)
    monkeypatch.setattr(iplog, "LOOKUP_DAILY_BUDGET", 3)
    for i in range(10):
        iplog.queue_geo_lookup(f"6.6.6.{i}")
    assert len(iplog._geo_queue) == 10
    await _drain()
    assert len(calls) == 3           # budget stoppade workern
    assert len(iplog._geo_queue) == 7  # resten ligger kvar till nästa dygn


def test_budget_resets_on_new_day(iso_geo, monkeypatch):
    monkeypatch.setattr(iplog, "_budget_day", "2000-01-01")
    monkeypatch.setattr(iplog, "_budget_used", 9999)
    assert iplog._budget_ok() is True  # datumbyte → reset
    assert iplog._budget_used == 0


# ── Kontrakt 5: kö-dedup + privata IP:er ────────────────────────────────

def test_queue_dedup_and_private_skipped(iso_geo):
    iplog.queue_geo_lookup("7.7.7.7")
    iplog.queue_geo_lookup("7.7.7.7")
    assert len(iplog._geo_queue) == 1
    iplog.queue_geo_lookup("192.168.1.1")
    iplog.queue_geo_lookup("127.0.0.1")
    iplog.queue_geo_lookup("testclient")
    iplog.queue_geo_lookup("")
    assert len(iplog._geo_queue) == 1


def test_record_visit_queues_only_unknown_ips(iso_geo):
    iplog._geo_cache["9.9.9.1"] = {"country": "X", "countryCode": "XX", "ts": time.time()}
    iplog.record_visit("9.9.9.1")   # känd+färsk → ingen kö
    assert iplog._geo_queue == set()
    iplog.record_visit("9.9.9.2")   # ny → köad
    assert "9.9.9.2" in iplog._geo_queue
    iplog.record_visit("9.9.9.2")   # redan köad → dedup
    assert len(iplog._geo_queue) == 1


def test_record_ip_queues_on_change_only(iso_geo):
    iplog.record_ip("u1", "8.8.4.4")
    assert "8.8.4.4" in iplog._geo_queue
    iplog._geo_queue.clear()
    iplog.record_ip("u1", "8.8.4.4")  # samma IP igen → ingen kö
    assert iplog._geo_queue == set()
    iplog.record_ip("u1", "8.8.8.9")  # IP-byte (login från ny ort) → kö
    assert "8.8.8.9" in iplog._geo_queue


# ── Kontrakt 6: worker-loopens mekanik ──────────────────────────────────

@pytest.mark.asyncio
async def test_worker_drains_full_queue(iso_geo, monkeypatch):
    calls = _fake_fetch_factory(monkeypatch)
    for i in range(9):
        iplog.queue_geo_lookup(f"10.10.{i}.1")  # OBS: 10.x ÄR privat-range-prefix!
    # 10.10.* matchar "10." → privata, köas aldrig — detta testar prefix-skyddet
    assert calls == []
    for i in range(9):
        iplog.queue_geo_lookup(f"11.11.{i}.1")
    await _drain()
    assert len(calls) == 9
    assert all(iplog.geo_cached(f"11.11.{i}.1")["countryCode"] == "SE" for i in range(9))


def test_queue_cap(iso_geo, monkeypatch):
    monkeypatch.setattr(iplog, "_GEO_QUEUE_MAX", 5)
    for i in range(20):
        iplog.queue_geo_lookup(f"12.12.{i}.1")
    assert len(iplog._geo_queue) == 5  # minnestak — resten köas vid nästa tillfälle


def test_persisted_cache_survives_reload(iso_geo):
    iplog._geo_cache["13.13.13.13"] = {"country": "Finland", "countryCode": "FI", "ts": time.time()}
    iplog._save()
    iplog._loaded = False
    iplog._geo_cache = {}
    iplog._load()
    assert iplog.geo_cached("13.13.13.13") == {"country": "Finland", "countryCode": "FI"}
