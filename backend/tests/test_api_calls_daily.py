"""2026-09-21 (rostad): admin-vyn ska visa antal API-calls per dag/vecka/månad.

Dagboken byggs i _scan_user_transcripts (daily: {YYYY-MM-DD: {calls, tokens}})
och aggregeras i /api/admin/stats till `api_daily`. Tester:

1. DM-post med tokens + fast pre-DM Guardian = 2 anrop på rätt dag.
2. Guardian-post (post-DM) med tokens = 1 anrop.
3. user-/roll-lösa poster utan tokens = 0 anrop.
4. UTC→lokal daglycka: 23:30Z en dag = nästa lokala dag (Stockholm, sommar +2).
5. /api/admin/stats: api_daily aggregerar över användare, sorterat.
"""
import json
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
def tmp_campaigns(tmp_path, monkeypatch):
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


def _write_transcript(root, user, cid, entries):
    td = root / user / cid / "transcripts"
    td.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in entries]
    (td / "session-1.jsonl").write_text("\n".join(lines), encoding="utf-8")


def test_daily_counts_llm_call_entries(tmp_campaigns):
    daily_expected = {
        # DM-anrop (1) + pre-DM guardian fast på samma post (1) = 2
        "2026-09-01": {"calls": 2, "tokens": (100 + 50) + (10 + 5)},
        # ren guardian post-DM = 1
        "2026-09-02": {"calls": 1, "tokens": 30 + 12},
    }
    _write_transcript(tmp_campaigns, "alice", "c1", [
        {"role": "user", "ts": "2026-09-01T10:00:00+00:00"},
        {"role": "assistant", "ts": "2026-09-01T10:00:30+00:00",
         "meta": {"model": "qwen3.8-max",
                  "tokens": {"prompt_tokens": 100, "completion_tokens": 50},
                  "guardian_pre_dm_tokens": {"prompt_tokens": 10, "completion_tokens": 5}}},
        {"role": "guardian", "ts": "2026-09-02T08:00:00+00:00",
         "meta": {"tokens": {"prompt_tokens": 30, "completion_tokens": 12}}},
        # tom user-post ska ALDRIG räknas som anrop
        {"role": "user", "ts": "2026-09-03T09:00:00+00:00"},
    ])
    scan = main._scan_user_transcripts("alice")
    assert scan["daily"] == daily_expected
    # total-tokenerna påverkas inte (befintna kontrakt)
    assert scan["total_tokens"] == 100 + 50 + 10 + 5 + 30 + 12


def test_daily_uses_local_stockholm_day(tmp_campaigns):
    # 23:30 UTC sommar = 01:30 lokal dagen efter → dagbokslut på LOKALT datum
    _write_transcript(tmp_campaigns, "bob", "c1", [
        {"role": "assistant", "ts": "2026-09-01T23:30:00+00:00",
         "meta": {"model": "qwen3.8-max",
                  "tokens": {"prompt_tokens": 10, "completion_tokens": 5}}},
    ])
    scan = main._scan_user_transcripts("bob")
    assert list(scan["daily"].keys()) == ["2026-09-02"]


def test_day_key_helpers():
    assert main._day_key("2026-09-01T10:00:00+00:00") == "2026-09-01"
    assert main._day_key("2026-09-01T23:30:00+00:00") == "2026-09-02"
    # naive timestamps treated as UTC
    assert main._day_key("2026-09-01T10:00:00") == "2026-09-01"
    assert main._day_key("") == ""
    assert main._day_key("garbage") == "garbage"[:10]


def test_admin_stats_api_daily_aggregates_users(tmp_campaigns, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    admin_u = {"password_hash": hash_password("x"), "role": "admin", "turn_cap": 50,
               "turns_used": 0, "created_at": "2026-08-01T10:00:00+00:00"}
    alice_u = dict(admin_u, role="player")
    main.save_users({"rostad": admin_u, "alice": alice_u})

    _write_transcript(tmp_campaigns, "alice", "c1", [
        {"role": "assistant", "ts": "2026-09-10T10:00:00+00:00",
         "meta": {"model": "qwen3.8-max",
                  "tokens": {"prompt_tokens": 100, "completion_tokens": 50}}},
    ])
    _write_transcript(tmp_campaigns, "rostad", "c1", [
        {"role": "assistant", "ts": "2026-09-10T12:00:00+00:00",
         "meta": {"model": "qwen3.8-flash",
                  "tokens": {"prompt_tokens": 200, "completion_tokens": 100}}},
        {"role": "assistant", "ts": "2026-09-11T12:00:00+00:00",
         "meta": {"model": "qwen3.8-flash",
                  "tokens": {"prompt_tokens": 10, "completion_tokens": 5}}},
    ])

    with TestClient(main.app) as client:
        r = client.get("/api/admin/stats",
                       cookies={"morkrets_token": create_token("rostad", "admin")})
        assert r.status_code == 200, r.text
        api_daily = r.json()["api_daily"]
        assert api_daily["2026-09-10"]["calls"] == 2
        assert api_daily["2026-09-10"]["tokens"] == 100 + 50 + 200 + 100
        assert api_daily["2026-09-11"]["calls"] == 1
        # sorterad kronologiskt
        assert list(api_daily.keys()) == sorted(api_daily.keys())
        # icke-admin nekas
        r403 = client.get("/api/admin/stats",
                          cookies={"morkrets_token": create_token("alice", "player")})
        assert r403.status_code == 403
