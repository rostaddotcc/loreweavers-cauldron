"""Global test fixtures (2026-08-08).

Turn-ledgern (strikt per-anrops-modell) skrivs till main._TURN_LEDGERS_DIR.
Utan autouse-fixture här skriver ALLA tester som rör chat/bilder riktiga
ledger-filer i backend/data/turn_ledgers/ — exakt samma läckage-klass som
users.json-läckan 2026-08-04. Denna fixture gäller för VARJE test i sviten.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def turn_ledgers_dir(tmp_path, monkeypatch):
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def ip_cache_files(tmp_path, monkeypatch):
    """Geo-/besökscachen får ALDRIG skrivas av tester (2026-09-27).

    main:s middleware anropar iplog som sparar via modul-globala sökvägar. Utan denna
    fixture skrev varje TestClient-baserad modul testkonton (ip="testclient") rakt in i
    den skarpa backend/data/ip_geo.json — samma läckageklass som users.json 2026-08-04
    och turn_ledgers 2026-08-08. Både filvägarna och de tre in-memory-storarna byts, så
    inget kan nå den riktiga filen ens via _save().
    """
    import iplog

    monkeypatch.setattr(iplog, "IP_GEO_FILE", tmp_path / "ip_geo.json")
    monkeypatch.setattr(iplog, "VISITS_FILE", tmp_path / "visits.json")
    # Tomma men formriktiga storar: _visit_store indexeras direkt (["by_day"] osv.),
    # så en bar {} ger KeyError i iplog.record().
    monkeypatch.setattr(iplog, "_ip_store", {}, raising=False)
    monkeypatch.setattr(iplog, "_geo_cache", {}, raising=False)
    monkeypatch.setattr(
        iplog,
        "_visit_store",
        {"total": 0, "by_day": {}, "by_ip": {}, "by_referrer": {}, "by_day_unique": {}},
        raising=False,
    )
    yield tmp_path
