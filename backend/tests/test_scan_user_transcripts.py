"""Regression: state.json (bakgrundstokens + TTS) läses EXAKT en gång per kampanj.

Blocket med `meta.unguarded_tokens` och `meta.tts_usage` låg tidigare inuti
per-sessionsfil-loopen → allt räknades en gång per `session-*.jsonl`, och
kampanjer utan transkriptfil tappades helt. Mätt mot skarp data 2026-09-28:
ingen kampanj hade både flera sessionsfiler och unguarded-data, så inga visade
tal ändrades av fixen — men en ny kampanj med två filer hade dubbelräknat
livstidstalen i admin-KPI:n.
"""
import json

import main


def _campaign(root, user, cid, unguarded=None, files=1, tts=None):
    d = root / user / cid
    (d / "transcripts").mkdir(parents=True, exist_ok=True)
    meta = {"campaign_name": cid}
    if unguarded:
        meta["unguarded_tokens"] = unguarded
    if tts:
        meta["tts_usage"] = tts
    (d / "state.json").write_text(json.dumps({"meta": meta}), encoding="utf-8")
    for i in range(files):
        (d / "transcripts" / f"session-{i:03d}.jsonl").write_text(
            json.dumps({"role": "assistant", "ts": "2026-09-27T20:00:00+00:00",
                        "meta": {"model": "test/model",
                                 "tokens": {"prompt_tokens": 100, "completion_tokens": 50}}}) + "\n",
            encoding="utf-8")
    return d


def test_unguarded_and_tts_are_counted_once_per_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path)
    _campaign(tmp_path, "alice", "kampanj-a",
              unguarded={"prompt_tokens": 1000, "completion_tokens": 200},
              files=2,
              tts={"calls": 3, "api_calls": 3, "chars": 100, "tokens": 0, "seconds": 5.0})

    scan = main._scan_user_transcripts("alice")

    assert scan["unguarded_tokens"] == 1200                  # en gång, inte två
    assert scan["total_tokens"] == 2 * 150 + 1200            # 2 filer × 150 + 1200
    assert scan["turns"] == 2
    assert scan["tts_usage"]["calls"] == 3                   # TTS också exakt en gång
    assert scan["tts_usage"]["seconds"] == 5.0
    # bakgrundstokens har ingen dag → de får aldrig hamna i dagboken
    assert scan["unguarded_tokens"] > 0
    assert sum(d["tokens"] for d in scan["daily"].values()) == 300


def test_campaign_without_transcript_files_still_counts_its_background_usage(tmp_path, monkeypatch):
    """Kampanjer vars transkriptfil saknas/roterats bort: bakgrundsanropen är
    fortfarande förbrukning och ska räknas (tidigare tappades de helt)."""
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path)
    _campaign(tmp_path, "bob", "kampanj-b",
              unguarded={"prompt_tokens": 500, "completion_tokens": 100}, files=0)

    scan = main._scan_user_transcripts("bob")

    assert scan["unguarded_tokens"] == 600
    assert scan["total_tokens"] == 600
    assert scan["daily"] == {}                               # ingen dag att lägga den på
