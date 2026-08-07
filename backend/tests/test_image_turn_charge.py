"""AI-bildgenerering kostar 1 turn — oavsett provider (2026-08-08).

StepFun-bilder var gratis (bugg): endast Wan-grenen drog en turn. Nu drar
varje bild exakt en turn (StepFun: _gate_turn_quota + _consume_turn).

autouse-fixtures: ALLA tester pekar users.json + kampanjer mot tmp —
ALDRIG riktig data.
"""
import base64
import sys
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
def turn_ledgers_dir(tmp_path, monkeypatch):
    """Peka turn-ledgern mot tmp (strikt per-anrops-modell 2026-08-08) —
    annars skriver bild-testerna riktiga ledger-filer i backend/data."""
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture(autouse=True)
def fake_stepfun(monkeypatch):
    """Stubba StepFun HTTP-et — ingen riktig API-nyckel/network i tester.

    Endpointen kör `async with httpx.AsyncClient(timeout=150) as client:
    resp = await client.post(...)` och läser resp.status_code samt
    resp.json()["data"][0]["b64_json"]. Patchar klassmetoden så både
    vault/me/campaign-grenarna träffas utan nätverk.
    """
    class _FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            b64 = base64.b64encode(b"fake-image-bytes").decode()
            return {"data": [{"b64_json": b64}]}

    async def _fake_post(self, *args, **kwargs):
        return _FakeResp()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", _fake_post)
    # Endpointen kräver STEPFUN_API_KEY (os.getenv) innan HTTP-anropet
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, fake_stepfun):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", email=None):
    u = {"password_hash": hash_password("secret123"), "role": role,
         "turn_cap": 50, "turns_used": 0, "turn_bonus": 0, "promo_bonus": 0,
         # 300 signup-promo redan utdelad → _consume_turn går direkt på
         # daglig cap (turns_used) så assertionerna blir deterministiska.
         "start_bonus_granted": True,
         # reset_date i FRAMTIDEN → ingen daglig rollover (alla icke-lifetime
         # tier = 24h-period) så turns_used förblir exakt som seedad.
         "reset_date": "2099-01-01", "subscription_status": "free",
         "subscription_until": None,
         # Support (3€): features.export + features_until i framtiden → tier1
         "features": {"export": True},
         "features_until": "2099-01-01",
         "wan_used_today": 0, "wan_reset_date": None,
         "created_at": "2026-08-01T10:00:00+00:00",
         "last_login": "2026-08-04T09:00:00+00:00"}
    if email:
        u["email"] = email
    main.save_users({username: u})


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _seed_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def test_stepfun_avatar_consumes_one_turn_per_image(client):
    """Varje StepFun-bild drar exakt 1 turn (var gratis före 2026-08-08)."""
    _seed("alice")
    _seed_campaign("alice")
    tok = _tok()

    r1 = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "player"},
        cookies={"morkrets_token": tok},
    )
    assert r1.status_code == 200, r1.text
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 1

    # Andra bilden → 2 turns totalt (fortfarande inom 50/day-cappen)
    r2 = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "player"},
        cookies={"morkrets_token": tok},
    )
    assert r2.status_code == 200, r2.text
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 2


def test_stepfun_avatar_gate_blocks_when_turns_exhausted(client):
    """0 turns kvar → 403 cap_reached (inte en gratisbild)."""
    _seed("alice")
    _seed_campaign("alice")
    # Förbruka hela dagliga capen + köpta → 0 turns kvar
    users = auth.load_users()
    users["alice"]["turns_used"] = 50
    users["alice"]["turn_bonus"] = 0
    users["alice"]["promo_bonus"] = 0
    auth.save_users(users)

    r = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "player"},
        cookies={"morkrets_token": _tok()},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["cap_reached"] is True
