"""🎤 /api/voice — röstinmatning via StepFun stepaudio-2.5-asr (2026-08-10).

- Transkriptet fyller bara chat-input → INGEN turn-förbrukning, men bokförs
  i state.meta.asr_usage för transparens.
- GRATIS sedan 2026-08-15 (följer StepFun TTS) — free tier får tala fritt.
- ffmpeg-konvertering mockas (riktig ffmpeg testas inte här).

autouse-fixtures: users.json + kampanjdata pekas mot tmp — skyddar riktig data
(users.json-incidenten 2026-08-04).
"""
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
from auth import hash_password  # noqa: E402


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


def _in_days(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _seed(username="alice", tier="tier1", turn_cap=50):
    features = {}
    if tier == "tier1":
        features = {"export": True}
    elif tier == "tier2":
        features = {"export": True, "all_models": True, "wan1080": True}
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": "player",
                   "turn_cap": turn_cap, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": _in_days(0),
                   "subscription_status": tier,
                   "subscription_until": _in_days(30) if tier != "free" else None,
                   "features": features,
                   "models_until": _in_days(30) if tier == "tier2" else None,
                   "start_bonus_granted": True,
                   "wan_used_today": 0, "wan_reset_date": _in_days(0)},
    })


def _login(client, username="alice"):
    r = client.post("/api/login", json={"username": username, "password": "secret123"})
    assert r.status_code == 200
    return r


def _post_voice(client, data: bytes = b"webm-bytes"):
    return client.post("/api/voice", files={"file": ("voice.webm", data, "audio/webm")})


# ── Tier-gate ─────────────────────────────────────────────────────────────

def test_voice_free_ok(client, monkeypatch):
    """free → 200 (röstinmatning är gratis sedan 2026-08-15); ingen turn."""
    _seed("alice", tier="free")
    main.store.create("alice", "Testkampanj", "en")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFF" + b"\x00" * 32000)
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "I open the door")
    r = _post_voice(client)
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "I open the door"
    assert main.load_users()["alice"]["turns_used"] == 0
    state = main.store.get("alice")
    assert state["meta"]["asr_usage"]["calls"] == 1


# ── Happy path ────────────────────────────────────────────────────────────

def test_voice_tier1_ok_no_turn(client, monkeypatch):
    """tier1 + mockad konvertering/ASR → 200 med text; ingen turn; asr_usage bokförs."""
    _seed("alice", tier="tier1")
    main.store.create("alice", "Testkampanj", "en")
    _login(client)
    seen = {}

    def _fake_wav(d):
        seen["conv"] = d
        return b"RIFF" + b"\x00" * 32000

    monkeypatch.setattr(main, "_to_wav_16k", _fake_wav)
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "I open the rusty door")
    r = _post_voice(client)
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "I open the rusty door"
    # Ingen turn — bara UI-hjälp
    assert main.load_users()["alice"]["turns_used"] == 0
    # Bokförd usage
    state = main.store.get("alice")
    asr = state["meta"]["asr_usage"]
    assert asr["calls"] == 1
    assert asr["api_calls"] == 1
    assert asr["seconds"] == pytest.approx(1.0, abs=0.01)  # 32000 B = 1 s 16k-mono


def test_voice_usage_visible_in_campaign_usage(client, monkeypatch):
    """asr_usage rullas upp i /api/campaign/usage under active_campaign.asr."""
    _seed("alice", tier="tier1")
    main.store.create("alice", "Testkampanj", "en")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFF" + b"\x00" * 32000)
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "hello")
    r = _post_voice(client)
    assert r.status_code == 200
    u = client.get("/api/campaign/usage")
    assert u.status_code == 200, u.text
    assert u.json()["active_campaign"]["asr"]["calls"] == 1


# ── Felhantering ──────────────────────────────────────────────────────────

def test_voice_empty_audio_400(client, monkeypatch):
    """Tom fil → 400."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFFwav")
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "x")
    r = _post_voice(client, data=b"")
    assert r.status_code == 400
    assert "Inget ljud" in r.json()["detail"]


def test_voice_bad_audio_400(client, monkeypatch):
    """ffmpeg kan inte avkoda → 400 (inte 500)."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"")
    r = _post_voice(client)
    assert r.status_code == 400
    assert "avkoda" in r.json()["detail"]


def test_voice_too_long_400(client, monkeypatch):
    """WAV > 60 s → 400 (kostnadsskydd)."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFF" + b"\x00" * (32000 * 61))
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "x")
    r = _post_voice(client)
    assert r.status_code == 400
    assert "60 sekunder" in r.json()["detail"]


def test_voice_oversize_400(client, monkeypatch):
    """Råfil > 10 MB → 400 innan ffmpeg ens körs."""
    _seed("alice", tier="tier1")
    _login(client)
    called = []
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: (called.append("conv") or b"RIFFwav"))
    r = _post_voice(client, data=b"x" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 400
    assert called == []


def test_voice_no_transcription_422(client, monkeypatch):
    """ASR returnerar tom text → 422."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFFwav")
    monkeypatch.setattr(main, "_asr_stepfun", lambda w: "")
    r = _post_voice(client)
    assert r.status_code == 422
    assert "transkription" in r.json()["detail"]


def test_voice_stepfun_error_502(client, monkeypatch):
    """StepFun krånglar → 502 (inte 500)."""
    _seed("alice", tier="tier1")
    _login(client)
    monkeypatch.setattr(main, "_to_wav_16k", lambda d: b"RIFFwav")

    def boom(w):
        raise RuntimeError("StepFun ASR HTTP 500: boom")
    monkeypatch.setattr(main, "_asr_stepfun", boom)
    r = _post_voice(client)
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]
