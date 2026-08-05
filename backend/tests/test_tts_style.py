"""Berättar-stil (premium: customize narrator voice) — /api/tts style-param.

autouse-fixtures: users.json pekas mot tmp — skyddar riktig data.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
from auth import hash_password  # noqa: E402


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


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", premium=False, tier=None, turn_cap=50):
    status = tier or ("tier2" if premium else "free")
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": "player",
                   "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": "2026-08-04",
                   "subscription_status": status,
                   "subscription_until": "2027-01-01" if status != "free" else None},
    })


def _login(client, username="alice"):
    r = client.post("/api/login", json={"username": username, "password": "secret123"})
    assert r.status_code == 200
    return r


# ── _tts_instruction: frasbyggande ────────────────────────────────────────

def test_instruction_no_style_returns_base():
    base = "Calm storytelling voice."
    assert main._tts_instruction(base, "") == base


def test_instruction_preset_prepends():
    out = main._tts_instruction("Calm storytelling voice.", "happy")
    assert out.startswith("Bright cheerful warm tone.")
    assert "Calm storytelling voice." in out


def test_instruction_custom_frase_used_verbatim():
    out = main._tts_instruction("Calm storytelling voice.", "whisper like a ghost")
    assert out.startswith("whisper like a ghost")
    assert "Calm storytelling voice." in out


def test_instruction_capped_at_128():
    base = "Speak Swedish with Standard Swedish pronunciation, natural rhythm. Dark fantasy storytelling, atmospheric and vivid."
    out = main._tts_instruction(base, "scary")
    assert len(out) <= 128
    assert out.startswith("Low ominous eerie tone")


# ── Premium-gate i /api/tts ───────────────────────────────────────────────

def test_style_ignored_for_free(client, monkeypatch):
    """Free-konto: style skickas men backend nollställer → synth får style=''.

    OBS: free → qwen fallbackar numera till stepfun (always free), så stepfun
    mockas här — själva style-gaten är samma oavsett leverantör.
    """
    _seed("alice", premium=False)
    _login(client)
    seen = {}
    def fake_synth(voice, text, style=""):
        seen["style"] = style
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", fake_synth)
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_synth)
    r = client.post("/api/tts", json={"text": "Hej världen", "voice": "male", "provider": "qwen", "style": "scary"})
    assert r.status_code == 200
    assert seen.get("style", "?") == ""


def test_stepfun_always_free_for_free(client, monkeypatch):
    """StepFun TTS är ALLTID GRATIS (rostad 2026-08-04) — free behåller stepfun."""
    _seed("alice", premium=False)
    _login(client)
    seen = {}
    def fake_qwen(voice, text, style=""):
        seen["provider"] = "qwen"
        return b"ID3fake"
    def fake_step(voice, text, style=""):
        seen["provider"] = "stepfun"
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", fake_qwen)
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_step)
    r = client.post("/api/tts", json={"text": "Hej", "voice": "male", "provider": "stepfun"})
    assert r.status_code == 200
    assert seen.get("provider") == "stepfun"  # always free


def test_qwen_falls_back_to_stepfun_for_free(client, monkeypatch):
    """Free/tier1: qwen TTS är tier2+ → tyst fallback till stepfun (always free)."""
    _seed("alice", premium=False)
    _login(client)
    seen = {}
    def fake_qwen(voice, text, style=""):
        seen["provider"] = "qwen"
        return b"ID3fake"
    def fake_step(voice, text, style=""):
        seen["provider"] = "stepfun"
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", fake_qwen)
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_step)
    # Unik text — TTS-cachen är processglobal och testet ovan kan ha cachat
    # samma text för stepfun (annars cache-hit utan synth-anrop).
    r = client.post("/api/tts", json={"text": "Hej qwen-gate", "voice": "male", "provider": "qwen"})
    assert r.status_code == 200
    assert seen.get("provider") == "stepfun"  # qwen → stepfun


def test_qwen_allowed_for_tier2(client, monkeypatch):
    """tier2: qwen TTS tillåten (premium-röst)."""
    _seed("alice", tier="tier2")
    _login(client)
    seen = {}
    def fake_qwen(voice, text, style=""):
        seen["provider"] = "qwen"
        return b"ID3fake"
    def fake_step(voice, text, style=""):
        seen["provider"] = "stepfun"
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_qwen_tts_retry", fake_qwen)
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_step)
    r = client.post("/api/tts", json={"text": "Hej", "voice": "male", "provider": "qwen"})
    assert r.status_code == 200
    assert seen.get("provider") == "qwen"  # tier2 behåller qwen


def test_style_passed_for_premium(client, monkeypatch):
    _seed("alice", premium=True)
    _login(client)
    seen = {}
    def fake_synth(voice, text, style=""):
        seen["style"] = style
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_synth)
    r = client.post("/api/tts", json={"text": "Hej världen", "voice": "male", "provider": "stepfun", "style": "happy"})
    assert r.status_code == 200
    assert seen.get("style") == "happy"


def test_style_affects_cache_key(client, monkeypatch):
    """Olika styles → olika cache-nycklar (får inte servera fel stil)."""
    _seed("alice", premium=True)
    _login(client)
    calls = []
    def fake_synth(voice, text, style=""):
        calls.append(style)
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_synth)
    client.post("/api/tts", json={"text": "Test", "voice": "male", "provider": "stepfun", "style": "happy"})
    client.post("/api/tts", json={"text": "Test", "voice": "male", "provider": "stepfun", "style": "scary"})
    assert len(calls) == 2  # båda syntetiseras — inte cache-hit med fel stil


def test_custom_style_passed_for_premium(client, monkeypatch):
    _seed("alice", premium=True)
    _login(client)
    seen = {}
    def fake_synth(voice, text, style=""):
        seen["style"] = style
        return b"ID3fake"
    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_synth)
    r = client.post("/api/tts", json={"text": "Hej", "voice": "male", "provider": "stepfun", "style": "whisper like a ghost"})
    assert r.status_code == 200
    assert seen.get("style") == "whisper like a ghost"
