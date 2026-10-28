"""Scene art (2026-10-27): opt-in illustration of the scene the player clicked.

Two things must hold and are tested here:
  1. the prompt is built from state + the clicked narration, with NO game
     statistics and no character name (numbers and names become scribbles in a
     painted image);
  2. the endpoint charges exactly one premium image + one turn (via
     _consume_wan_quota), writes the file, records it in state["images"] so the
     campaign export picks it up, and refuses cleanly when the tier or campaign
     is missing.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from scene_art import MAX_PROMPT, build_scene_prompt, clean_excerpt

STATE = {
    "meta": {"campaign_id": "cid-9", "turn_count": 42, "language": "en"},
    "world": {"current_location": "Sunwarden Keep", "time": "Dusk, the gates half open",
              "weather": "cold rain"},
    "character": {"name": "Pemba"},
    "images": [],
}


# ── the prompt ─────────────────────────────────────────────────────────────

def test_prompt_uses_state_and_the_clicked_narration():
    prompt = build_scene_prompt(STATE, "The parley breaks and a rider spurs toward the ford.")
    assert "Sunwarden Keep" in prompt
    assert "Dusk" in prompt
    assert "cold rain" in prompt
    assert "parley" in prompt
    assert "dark fantasy oil painting" in prompt


def test_prompt_carries_no_game_statistics():
    # Siffror i en bildprompt blir klotter i bilden.
    prompt = build_scene_prompt(
        STATE,
        "You take 7 damage (HP 12/20) and the goblin, AC 15, rolls again in 3 turns.",
    )
    for bad in ("12/20", "AC 15", "3 turns", "7 damage"):
        assert bad not in prompt, bad


def test_prompt_has_no_character_name():
    prompt = build_scene_prompt(STATE, "The hall is empty.")
    assert "Pemba" not in prompt


def test_protocol_tags_and_markdown_are_stripped():
    raw = "**[KAST: SMIDIGHET 14|DC 12]** The rope *snaps* and the bridge `groans`."
    cleaned = clean_excerpt(raw)
    assert "KAST" not in cleaned
    assert "*" not in cleaned and "`" not in cleaned
    assert "rope" in cleaned and "bridge" in cleaned


def test_long_narration_is_cut_at_a_sentence_boundary():
    long = ("The gate opens. " * 60).strip()
    cleaned = clean_excerpt(long)
    assert len(cleaned) <= 420
    assert cleaned.endswith(".")


def test_empty_state_still_yields_a_usable_prompt():
    prompt = build_scene_prompt({}, "")
    assert prompt and "Scene:" in prompt
    assert len(prompt) <= MAX_PROMPT


# ── the endpoint ───────────────────────────────────────────────────────────

def _wire(monkeypatch, tmp_path, *, tier_error=None, campaign=STATE):
    state = {"meta": dict(STATE["meta"]), "world": dict(STATE["world"]),
             "character": dict(STATE["character"]), "images": []}
    saved = {}
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", tmp_path)
    monkeypatch.setattr(main, "_get_current_user", lambda token=None: {"sub": "qa"})
    monkeypatch.setattr(main.store, "get", lambda user: state if campaign else None)
    monkeypatch.setattr(main.store, "save", lambda s: saved.setdefault("state", s))

    def gate(username, provider, payload=None):
        if tier_error:
            raise tier_error
    monkeypatch.setattr(main, "_require_image_gen_tier", gate)

    calls = {"quota": 0}
    monkeypatch.setattr(main, "_consume_wan_quota", lambda u: calls.__setitem__("quota", calls["quota"] + 1))
    monkeypatch.setattr(main, "_wan_model_and_size", lambda u: ("wan2.7-image", "1024*1024"))
    monkeypatch.setattr(main, "_add_image_gen", lambda u, m="": None)

    async def fake_image(model, prompt, size, seed):
        calls["prompt"] = prompt
        calls["model"] = model
        return b"\x89PNG\r\n\x1a\nfake"
    monkeypatch.setattr(main, "_token_plan_image", fake_image)
    return state, calls


def test_endpoint_paints_and_records_the_image(monkeypatch, tmp_path):
    state, calls = _wire(monkeypatch, tmp_path)
    res = asyncio.run(main.generate_scene_image(
        {"text": "A rider spurs toward the ford.", "provider": "wan"}, None))
    assert res["ok"] is True
    assert res["provider"] == "wan"
    assert res["url"].startswith("/api/campaign/scene/scene-0042-")
    assert calls["quota"] == 1                      # 1 bild + 1 turn, en gång
    assert "Sunwarden Keep" in calls["prompt"]
    assert len(state["images"]) == 1
    entry = state["images"][0]
    assert Path(entry["path"]).is_file()            # filen finns på disk
    assert entry["turn"] == 42 and entry["url"] == res["url"]
    # Exporten läser state["images"][].path → scenen följer med ut
    assert Path(entry["path"]).parent.name == "scenes"


def test_locked_tier_is_refused_before_anything_is_charged(monkeypatch, tmp_path):
    state, calls = _wire(monkeypatch, tmp_path, tier_error=HTTPException(403, "feature_locked"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.generate_scene_image({"text": "x"}, None))
    assert exc.value.status_code == 403
    assert calls["quota"] == 0
    assert state["images"] == []


def test_no_campaign_is_a_404(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, campaign=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.generate_scene_image({"text": "x"}, None))
    assert exc.value.status_code == 404


def test_daily_cap_refusal_propagates(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)

    def cap(username):
        raise HTTPException(403, "Daily image cap reached: 10 premium images/day.")
    monkeypatch.setattr(main, "_consume_wan_quota", cap)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.generate_scene_image({"text": "x"}, None))
    assert exc.value.status_code == 403
    assert "Daily image cap" in str(exc.value.detail)