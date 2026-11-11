"""2026-08-06: admin 'Calls by provider' ska visa ALLA anropade modeller —
inkl. TTS- och bildmodeller (by_model-spårning).

autouse-fixtures: ALDRIG riktig data (users.json + kampanjer → tmp).
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
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player"):
    u = {"password_hash": hash_password("secret123"), "role": role,
         "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
         "reset_date": "2026-08-04", "subscription_status": "free",
         "subscription_until": None, "created_at": "2026-08-01T10:00:00+00:00",
         "last_login": "2026-08-04T09:00:00+00:00"}
    main.save_users({username: u})


def _tok(username="alice", role="player"):
    return create_token(username, role)


def test_admin_stats_includes_tts_and_image_models(client):
    _seed("rostad", role="admin")
    _seed("alice")
    main.store.create("alice", name="Test Campaign", language="en")

    # Simulera användning: DM-LLM i transkriptet + TTS + bildgen (by_model)
    state = main.store.get("alice")
    assert state is not None
    state["meta"]["tts_usage"] = {
        "calls": 4, "api_calls": 3, "chars": 1200, "tokens": 300, "seconds": 30.0,
        "by_model": {"qwen-audio-3.0-tts-plus": 2, "stepaudio-2.5-tts": 2},
    }
    # Account-usage: bildgen + en DM-post i transkriptet
    main._mutate_account_usage("alice", lambda acc: acc["image_gen"].update(
        {"calls": 3, "by_model": {"wan2.7-image": 2, "step-image-edit-2": 1}}))
    main.store.append_message(state, "assistant", "Hello world",
                              meta={"model": "qwen3.8-max", "tokens": {"prompt_tokens": 100, "completion_tokens": 50}})
    main.store.save(state)

    r = client.get("/api/admin/stats", cookies={"morkrets_token": _tok("rostad", "admin")})
    assert r.status_code == 200, r.text
    data = r.json()

    models = data["models"]
    # TTS-modeller finns med anrop
    assert models["qwen-audio-3.0-tts-plus"]["calls"] == 2
    assert models["qwen-audio-3.0-tts-plus"]["provider"] == "dashscope"
    assert models["stepaudio-2.5-tts"]["calls"] == 2
    assert models["stepaudio-2.5-tts"]["provider"] == "stepfun"
    # Bildmodeller finns med anrop
    assert models["wan2.7-image"]["calls"] == 2
    assert models["wan2.7-image"]["provider"] == "dashscope"
    assert models["step-image-edit-2"]["calls"] == 1
    assert models["step-image-edit-2"]["provider"] == "stepfun"
    # Vanlig DM-modell fortfarande där
    assert models["qwen3.8-max"]["calls"] == 1

    # Provider-aggregering: dashscope har TTS(qwen)+wan bildgen
    provs = data["providers"]
    assert provs["dashscope"]["calls"] >= 4
    assert provs["stepfun"]["calls"] >= 3


def test_transcript_exposes_guardian_running(client):
    _seed("alice")
    main.store.create("alice", name="Test Campaign", language="en")
    r = client.get("/api/campaign/transcript", cookies={"morkrets_token": _tok("alice")})
    assert r.status_code == 200, r.text
    assert "guardian_running" in r.json()
    assert r.json()["guardian_running"] is False
