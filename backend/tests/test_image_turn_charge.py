"""AI-bildgenerering kostar 1 turn — oavsett motor (2026-08-08).

2026-09-27 (ny prissättning): ALL bildgenerering ligger dessutom bakom
10€-unlåset — testerna seedar därför features.all_models (unlock10-form).
Varje bild drar exakt en turn (_consume_wan_quota → _gate_turn_quota +
_consume_turn).

2026-10-10: StepFun step-image-edit-2 är pensionerad (leverantören serverar
inte bild-API:n) — motorerna är Wan 2.7 / Qwen Image 3 Pro (Token Plan).
Steget normaliseras till wan i alla tre avatar-endpoints.

autouse-fixtures: ALLA tester pekar users.json + kampanjer mot tmp —
ALDRIG riktig data.
"""
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
def fake_token_plan_image(monkeypatch):
    """Stubba Token Plan (Wan/Qwen-bild)— ingen riktig API-nyckel/network.

    _token_plan_image kör POST mot DashScope-endpointen (output-choices-
    shape med bild-URL) och sedan en GET för att hämta bilden. Patchar
    httpx.AsyncClient klassmetoderna så alla tre avatar-grenarna
    (campaign/vault/me) träffas utan nätverk.
    """
    class _FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"output": {"choices": [{"message": {"content": [
                {"type": "image", "image": "http://fake.example/img.png"}]}}]}}

        def raise_for_status(self):
            return None

    async def _fake_post(self, *args, **kwargs):
        return _FakeResp()

    async def _fake_get(self, *args, **kwargs):
        class _DL:
            status_code = 200
            content = b"fake-image-bytes"

            def raise_for_status(self):
                pass
        return _DL()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr(main.httpx.AsyncClient, "get", _fake_get)
    # Endpointen kräver DASHSCOPE_API_KEY (os.getenv) innan HTTP-anropet
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, fake_token_plan_image):
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
         # 10€-unlock (2026-09-27): features utan utgångsdatum → tier2 permanent
         "features": {"export": True, "all_models": True, "wan1080": True, "unlock10": True},
         "features_until": None,
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


def test_wan_avatar_consumes_one_turn_per_image(client):
    """Varje wan-bild drar exakt 1 turn (dubbelgrind: dagskvot + turn)."""
    _seed("alice")
    _seed_campaign("alice")
    tok = _tok()

    r1 = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "wan", "kind": "player"},
        cookies={"morkrets_token": tok},
    )
    assert r1.status_code == 200, r1.text
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 1

    # Andra bilden → 2 turns totalt (fortfarande inom 50/day-cappen)
    r2 = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "wan", "kind": "player"},
        cookies={"morkrets_token": tok},
    )
    assert r2.status_code == 200, r2.text
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 2


def test_legacy_stepfun_provider_normalizes_to_wan(client):
    """2026-10-10: 'stepfun' (pensionerad bildmotor) → wan, ingen StepFun-
    HTTP-väg finns kvar. Anropet drar fortfarande exakt 1 turn."""
    _seed("alice")
    _seed_campaign("alice")

    r = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "player"},
        cookies={"morkrets_token": _tok()},
    )
    assert r.status_code == 200, r.text
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 1
    assert users["alice"]["wan_used_today"] == 1


def test_avatar_gate_blocks_when_turns_exhausted(client):
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
        json={"provider": "wan", "kind": "player"},
        cookies={"morkrets_token": _tok()},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["cap_reached"] is True
