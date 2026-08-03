"""Test: kontots totals (LLM-tokens + turns + TTS + char-creation + image-gen)
överlever kampanjradering.

Scenario: spelare har förbrukning i en kampanj, raderar kampanjen → den
beständiga per-konto-ackumulatorn (_account_usage.json) bevarar totalen så
_scan_user_transcripts (och därmed admin-vyn / account_total) fortfarande
visar den spenderade summan.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


TEST_TTS = {"calls": 12, "api_calls": 9, "chars": 1234, "tokens": 308, "seconds": 45.0}


@pytest.fixture
def tmp_campaigns(tmp_path, monkeypatch):
    """Peka CAMPAIGNS_DIR mot en temporär mapp så inget riktigt data rörs."""
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path)
    # Ackumulatorlås är globalt — återställs inte, men det är ok (per-test-mapp).
    return tmp_path


def _write_campaign(root, user, cid, tts=None, transcript_tokens=None, unguarded=None):
    cdir = root / user / cid
    cdir.mkdir(parents=True, exist_ok=True)
    state = {"meta": {"campaign_id": cid, "user": user}}
    if tts:
        state["meta"]["tts_usage"] = dict(tts)
    if unguarded:
        state["meta"]["unguarded_tokens"] = unguarded
    (cdir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    # _scan_user_transcripts hoppar över kampanjer utan transcripts-katalog
    td = cdir / "transcripts"
    td.mkdir(exist_ok=True)
    lines = []
    if transcript_tokens:
        for pt, ct in transcript_tokens:
            lines.append(json.dumps({
                "role": "assistant",
                "meta": {"tokens": {"prompt_tokens": pt, "completion_tokens": ct,
                                    "total_tokens": pt + ct}},
            }))
    (td / "session-1.jsonl").write_text("\n".join(lines), encoding="utf-8")
    return cdir


def test_deleted_campaign_tokens_turns_and_tts_survive_deletion(tmp_campaigns):
    user = "glebirth"
    cid = "camp-1"
    _write_campaign(
        tmp_campaigns, user, cid, tts=TEST_TTS,
        transcript_tokens=[(1000, 500), (800, 200)],
        unguarded={"prompt_tokens": 300, "completion_tokens": 100},
    )

    # Total före radering
    scan_before = main._scan_user_transcripts(user)
    assert scan_before["total_tokens"] == 1000 + 500 + 800 + 200 + 300 + 100
    assert scan_before["turns"] == 2
    assert scan_before["tts_usage"]["tokens"] == TEST_TTS["tokens"]

    # Simulera delete_campaign: snapshot + ackumulera, radera katalogen
    snap = main._campaign_usage_snapshot(user, cid)
    main._add_deleted_campaign(user, snap)
    shutil.rmtree(tmp_campaigns / user / cid)

    assert not (tmp_campaigns / user / cid).exists()

    # Total efter radering måste fortfarande visa hela förbrukningen
    scan_after = main._scan_user_transcripts(user)
    assert scan_after["total_tokens"] == scan_before["total_tokens"]
    assert scan_after["turns"] == 2
    assert scan_after["tts_usage"]["tokens"] == TEST_TTS["tokens"]
    assert scan_after["tts_usage"]["calls"] == TEST_TTS["calls"]
    assert scan_after["deleted_campaigns"]["total_tokens"] == scan_before["total_tokens"]


def test_deleted_campaign_accumulates_across_two_campaigns(tmp_campaigns):
    user = "arla"
    _write_campaign(tmp_campaigns, user, "c1", tts=TEST_TTS, transcript_tokens=[(100, 50)])
    _write_campaign(tmp_campaigns, user, "c2", tts={"calls": 3, "api_calls": 2, "chars": 100, "tokens": 25, "seconds": 5.0},
                    transcript_tokens=[(10, 5)])

    snap1 = main._campaign_usage_snapshot(user, "c1")
    snap2 = main._campaign_usage_snapshot(user, "c2")
    main._add_deleted_campaign(user, snap1)
    main._add_deleted_campaign(user, snap2)
    shutil.rmtree(tmp_campaigns / user / "c1")
    shutil.rmtree(tmp_campaigns / user / "c2")

    scan = main._scan_user_transcripts(user)
    # c1: 150 tkn + 308 tts; c2: 15 tkn + 25 tts
    assert scan["total_tokens"] == 150 + 15
    assert scan["tts_usage"]["tokens"] == TEST_TTS["tokens"] + 25
    assert scan["tts_usage"]["calls"] == TEST_TTS["calls"] + 3


def test_character_creation_and_image_gen_accumulate(tmp_campaigns):
    user = "lora"
    main._add_character_creation(user, {"total_tokens": 1200})
    main._add_character_creation(user, {"total_tokens": 800})
    main._add_image_gen(user)
    main._add_image_gen(user)
    main._add_image_gen(user)

    scan = main._scan_user_transcripts(user)
    assert scan["character_creation"]["tokens"] == 2000
    assert scan["character_creation"]["calls"] == 2
    assert scan["image_gen"]["calls"] == 3


def test_character_creation_ignores_zero_usage(tmp_campaigns):
    user = "nadia"
    main._add_character_creation(user, {"total_tokens": 0})
    assert main._scan_user_transcripts(user)["character_creation"]["calls"] == 0


def test_migration_from_old_deleted_tts_file(tmp_campaigns):
    user = "migrate"
    (tmp_campaigns / user).mkdir(parents=True, exist_ok=True)
    # Gammal fil (2026-08-03 feature)
    (tmp_campaigns / user / "_deleted_tts.json").write_text(
        json.dumps({"calls": 5, "api_calls": 4, "chars": 500, "tokens": 125, "seconds": 10.0}),
        encoding="utf-8",
    )
    acc = main._load_account_usage(user)
    assert acc["deleted"]["tts"]["tokens"] == 125
    assert acc["deleted"]["tts"]["calls"] == 5