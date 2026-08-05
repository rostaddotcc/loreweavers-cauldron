"""2026-08-05 v3: 1-konto-per-IP vid registrering.

Rostad: "Vi behöver också blockera 1 konto per IP får skapas."
- Register blockerar en andra registrering från samma PUBLIKA IP (403).
- Privata IP:er (LAN/localhost) hoppas över — blockering är meningslös bakom NAT.
- iplog._ip_store isoleras till tmp så riktig data aldrig rörs (autouse).

Ingen riktig data rörs: users.json + kampanj-data + ip-store pekas om till tmp.
"""

import sys
import json
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
def ip_store(tmp_path, monkeypatch):
    """Isolera iplog: tmp-fil + ren in-memory-store varje test."""
    f = tmp_path / "ip_geo.json"
    monkeypatch.setattr(iplog, "IP_GEO_FILE", f)
    monkeypatch.setattr(iplog, "_loaded", False)
    monkeypatch.setattr(iplog, "_ip_store", {})
    monkeypatch.setattr(iplog, "_geo_cache", {})
    return f


@pytest.fixture
def client(users_file, campaigns_dir, ip_store):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _register(username, ip=None):
    """Registrera via en FRISK TestClient per anrop.

    TestClient:s cookie-jar läcker morkrets_token mellan requests — en
    registrerad användares cookie på nästa register-request får iplog-
    middlewaven att boka in användaren under FEL IP och triggar 1-konto-
    per-IP-blocket. Färsk client = tom cookie-jar = korrekt isolering.
    """
    from fastapi.testclient import TestClient
    headers = {"X-Forwarded-For": ip} if ip else {}
    with TestClient(main.app) as c:
        return c.post("/api/register",
                      json={"username": username, "password": "secret123"},
                      headers=headers)


def test_second_account_same_public_ip_blocked(ip_store):
    r1 = _register("alice", ip="1.2.3.4")
    assert r1.status_code == 200, r1.text
    r2 = _register("bob", ip="1.2.3.4")
    assert r2.status_code == 403
    assert "already exists" in r2.json()["detail"].lower()


def test_different_ip_allowed(ip_store):
    _register("alice", ip="1.2.3.4")
    r = _register("bob", ip="9.9.9.9")
    assert r.status_code == 200, r.text
    assert "bob" in main.load_users()


def test_private_ip_skips_block(ip_store):
    """LAN/localhost-IP:er blockerar inte — annars bryts lokal utveckling."""
    r1 = _register("alice", ip="192.168.1.10")
    assert r1.status_code == 200, r1.text
    r2 = _register("bob", ip="192.168.1.10")
    assert r2.status_code == 200, r2.text
    assert "bob" in main.load_users()


def test_no_xff_header_uses_direct_ip(ip_store):
    """Utan X-Forwarded-For används request.client.host → TestClient = localhost (privat)."""
    r1 = _register("alice")
    assert r1.status_code == 200, r1.text
    r2 = _register("bob")
    assert r2.status_code == 200, r2.text
    assert "bob" in main.load_users()


def test_existing_user_ip_in_store_blocks_new(ip_store):
    """Befintliga användares IP:er (från autentiserade requests) räknas också."""
    iplog.record_ip("oldplayer", "77.88.99.10")
    r = _register("newbie", ip="77.88.99.10")
    assert r.status_code == 403
    assert "already exists" in r.json()["detail"].lower()


def test_register_records_ip_for_new_user(ip_store):
    _register("alice", ip="1.2.3.4")
    assert iplog.get_user_ip("alice") == "1.2.3.4"
