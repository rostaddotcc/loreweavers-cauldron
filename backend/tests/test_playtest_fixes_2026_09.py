"""Playtest-fixar 2026-09 (röd 400 på logbook-refresh + TTS-röster utan grind).

Täcker:
  1) POST /api/campaign/logbook/refresh-today: ny kampanj utan dag-entries
     → 200 {ok: True, refresh: 0} i stället för HTTP 400 (riktiga fel är
     kvar: ingen kampanj → 404).
  2) GET /api/tts/voices: samma tier-grind som POST /api/tts — free ser
     endast stepfun, Patron (tier2/lifetime) och admin ser qwen.
  3) Bonus: _extraction_call_RETRY med temp 0.1 på samma modell INNAN
     fallback till EXTRACTION_MODEL, båda stegen loggade vid WARNING.

Test-isolering (backend-test-isolation-pitfalls): INGEN /api/register —
användare seedas direkt i users.json (tmp-monterad via auth.USERS_FILE).
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
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


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(username, role="player", *, features=None, features_until=None,
          subscription_status="free"):
    users = main.load_users()
    users[username] = {
        "password_hash": hash_password("secret123"),
        "role": role,
        "turn_cap": 50, "turns_used": 0, "turn_bonus": 0, "promo_bonus": 0,
        "reset_date": _today(),
        "subscription_status": subscription_status,
        "features": features or {},
        "features_until": features_until,
        "start_bonus_granted": True,
        "wan_used_today": 0, "wan_reset_date": _today(),
    }
    main.save_users(users)
    return create_token(username, role)


def _tok_player(username="alice"):
    return _seed(username)


def _tok_free():
    return _seed("frile")


def _tok_patron():
    return _seed("patron", features={"export": True, "all_models": True},
                 features_until=_in_days(30))


def _tok_lifetime():
    return _seed("livetime", subscription_status="lifetime")


def _tok_admin():
    return _seed("the_admin", role="admin")


# ── 1) logbook refresh-today: tomt ≠ fel ─────────────────────────────────

def test_refresh_today_no_day_entries_is_200(client):
    tok = _tok_player()
    main.store.create("alice", name="Fresh", language="en")
    r = client.post("/api/campaign/logbook/refresh-today",
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("refreshed") == 0


def test_refresh_today_no_campaign_still_404(client):
    tok = _tok_player()  # ingen kampanj skapad
    r = client.post("/api/campaign/logbook/refresh-today",
                    cookies={"morkrets_token": tok})
    assert r.status_code == 404


def test_refresh_today_empty_campaign_spends_no_turn(client):
    tok = _tok_player()
    main.store.create("alice", name="Fresh", language="en")
    client.post("/api/campaign/logbook/refresh-today",
                cookies={"morkrets_token": tok})
    assert main.load_users()["alice"]["turns_used"] == 0


# ── 2) /api/tts/voices: samma grind som /api/tts ─────────────────────────

def _provider_ids(client, tok):
    r = client.get("/api/tts/voices", cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "providers" in body and "default_provider" in body
    for p in body["providers"]:
        assert set(p) == {"id", "name", "voices"}  # oförändrad form
    return [p["id"] for p in body["providers"]], body


def test_voices_free_user_sees_only_stepfun(client):
    ids, body = _provider_ids(client, _tok_free())
    assert ids == ["stepfun"]
    assert body["default_provider"] == main.TTS_DEFAULT_PROVIDER


def test_voices_stepfun_voices_intact_for_free(client):
    _, body = _provider_ids(client, _tok_free())
    step = body["providers"][0]
    real_ids = {v["id"] for v in main.TTS_PROVIDERS["stepfun"]["voices"]}
    assert {v["id"] for v in step["voices"]} == real_ids
    assert step["voices"], "stepfun must never be emptied"


def test_voices_patron_sees_qwen(client):
    ids, _ = _provider_ids(client, _tok_patron())
    assert "qwen" in ids and "stepfun" in ids


def test_voices_lifetime_sees_qwen(client):
    ids, _ = _provider_ids(client, _tok_lifetime())
    assert "qwen" in ids


def test_voices_admin_keeps_everything(client):
    ids, _ = _provider_ids(client, _tok_admin())
    assert set(ids) == set(main.TTS_PROVIDERS)


def test_voices_gate_mirrors_tts_call_gate(client):
    """free: qwen-röster osynliga OCH qwen-anrop 403 — samma villkor."""
    tok = _tok_free()
    ids, _ = _provider_ids(client, tok)
    assert "qwen" not in ids
    r = client.post("/api/tts", json={"text": "hello", "provider": "qwen"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 403
    assert "Patron" in r.json()["detail"]
    # patron: bade synlig rost och tillatet anrop (anropet mockas ej —
    # bara grinden prover vi, sa langt som till 400/403-leget)
    ptok = _tok_patron()
    pids, _ = _provider_ids(client, ptok)
    assert "qwen" in pids


def test_voices_unauthenticated_is_401(client):
    r = client.get("/api/tts/voices")
    assert r.status_code == 401


# ── 3) extraction-retry fore fallback ────────────────────────────────────

@pytest.mark.asyncio
async def test_extraction_retry_before_fallback(monkeypatch):
    calls = []
    seq = ["Let me analyze this carefully…",        # prat (ingen JSON)
           "Still rambling, here is my analysis.",  # retry temp 0.1 → prat
           '{"day": 3, "title": "ok"}']             # fallback → JSON

    async def fake_call(model, messages, temperature=0.8, max_tokens=300,
                        usage_out=None, **kw):
        calls.append((model, temperature))
        return seq[len(calls) - 1]

    warnings = []
    monkeypatch.setattr(main, "_call_llm", fake_call)
    monkeypatch.setattr(main, "_extraction_model_for", lambda s: "chatty-x")
    monkeypatch.setattr(main.logger, "warning",
                        lambda msg, *a, **k: warnings.append(msg % a))
    assert main.EXTRACTION_MODEL != "chatty-x"

    raw = await main._extraction_call({}, [{"role": "user", "content": "go"}],
                                      {}, temperature=0.3)

    # 1) samma modell, 2) retry temp 0.1 samma modell, 3) fallback
    assert calls == [("chatty-x", 0.3), ("chatty-x", 0.1),
                     (main.EXTRACTION_MODEL, 0.3)]
    assert raw.strip().startswith("{")
    retry_logs = [w for w in warnings if "temperature=0.1" in w]
    fb_logs = [w for w in warnings if "fallback" in w]
    assert len(retry_logs) == 1 and "chatty-x" in retry_logs[0]
    assert len(fb_logs) == 1 and "chatty-x" in fb_logs[0] \
        and main.EXTRACTION_MODEL in fb_logs[0]


@pytest.mark.asyncio
async def test_extraction_no_retry_when_json_on_first_call(monkeypatch):
    calls = []

    async def fake_call(model, messages, temperature=0.8, max_tokens=300,
                        usage_out=None, **kw):
        calls.append((model, temperature))
        return '{"day": 1}'

    monkeypatch.setattr(main, "_call_llm", fake_call)
    monkeypatch.setattr(main, "_extraction_model_for", lambda s: "chatty-x")
    raw = await main._extraction_call({}, [{"role": "user", "content": "go"}],
                                      {}, temperature=0.3)
    assert raw == '{"day": 1}'
    assert calls == [("chatty-x", 0.3)]
