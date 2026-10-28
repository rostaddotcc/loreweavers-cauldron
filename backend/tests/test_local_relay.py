"""🏮 Local AI / Ollama-relay (v1): prepare/commit för DM-steget.

Täcker (design: vault dnd-llm-local-ollama-impl-2026-09, §5.1):
  - _clamp_player_model släpper local:* för ALLA tiers (inkl. free)
  - _validate_model_id: local:* → True
  - _call_llm / _call_llm_with_reasoning / _stream_llm hårdavvisar local:*
  - prepare happy path → exakt kontraktsform (step_id/kind/ollama/deadline)
  - 400 (icke-local/okänd), 401, 404, 503 (LOCAL_AI_ENABLED av)
  - commit happy path → samma JSON-shape som /api/chat; local_dm-ledgerrad
    (turns 0, turns_used orörd)
  - engångs-steg (andra commit → 410), TTL-utgång → 410, turn-drift → 409,
    främmande ägare → 403, dagligt cap → 429
  - [SÖK:]-tagg i relä-svar: rensas utan hus-anrop/turn-drift

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger mot tmp —
ALDRIG riktig data (samma mönster som test_orfree_models.py).
"""
import asyncio
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import local_relay  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402

# Originalen FANGADE VID IMPORT (före autouse-llm_mocks monkeypatch:ar) —
# hårdavvisningstesterna måste köra den RIKTIGA routingen.
_ORIG_CALL_LLM = main._call_llm
_ORIG_CALL_LLM_REASONING = main._call_llm_with_reasoning
_ORIG_STREAM_LLM = main._stream_llm

LOCAL_ID = "local:qwen3:14b"


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
def llm_mocks(monkeypatch):
    async def fake_dm(model_id, messages, **kw):
        return ("The wind howls.", "n/a", {"total_tokens": 1})

    async def noop(*a, **k):
        return None

    async def no_memory(*a, **k):
        return {"text": "", "facts_sent": 0, "rag_sent": 0, "timing_s": 0.0}

    monkeypatch.setattr(main, "_call_llm_with_reasoning", fake_dm)
    monkeypatch.setattr(main, "guardian_check_roll", noop)
    monkeypatch.setattr(main, "_retrieve_relevant_memory", no_memory)
    monkeypatch.setattr(main, "_guardian_post_dm", noop)
    monkeypatch.setattr(main, "_post_turn_tasks", noop)


@pytest.fixture(autouse=True)
def local_env(monkeypatch):
    """Relät PÅ för hela sviten (per anrop, ingen nätverks-LLM). Steg-lagret
    tömt före varje test så inget läcker mellan tester."""
    monkeypatch.setenv("LOCAL_AI_ENABLED", "1")
    monkeypatch.delenv("LOCAL_STEP_TTL_SECONDS", raising=False)
    monkeypatch.delenv("LOCAL_DM_DAILY_CAP", raising=False)
    local_relay.clear_steps()
    yield
    local_relay.clear_steps()


@pytest.fixture
def client(users_file, campaigns_dir, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed_player(username="alice"):
    users = main.load_users()
    users[username] = {
        "password_hash": hash_password("secret123"),
        "role": "player",
        "turn_cap": 50,
        "turns_used": 0,
        "turn_bonus": 0,
        "promo_bonus": 0,
        "subscription_status": "free",
    }
    main.save_users(users)
    return create_token(username, "player")


def _make_campaign(username):
    main.store.create(username, name="Local Test Campaign", language="en")


def _prepare(client, tok, message="Jag tittar mig omkring", model_id=LOCAL_ID, **kw):
    body = {"message": message, "model_id": model_id}
    body.update(kw)
    return client.post("/api/chat/local/prepare", json=body,
                       cookies={"morkrets_token": tok})


def _commit(client, tok, step_id, content="Du står på en kulle. Vinden viner.", **kw):
    body = {"step_id": step_id, "content": content}
    body.update(kw)
    return client.post("/api/chat/local/commit", json=body,
                       cookies={"morkrets_token": tok})


# ── Clamp / validering / hårdavvisning ─────────────────────────────────

def test_clamp_allows_local_for_all_tiers():
    for tier in ("free", "tier1", "tier2", "lifetime", None, "whatever"):
        assert main._clamp_player_model(LOCAL_ID, tier=tier) == LOCAL_ID, tier


def test_validate_model_id_accepts_local():
    assert main._validate_model_id(LOCAL_ID) is True
    assert main._validate_model_id("local:deepseek-r1:8b") is True
    assert main._validate_model_id("step-3.7-flash") is True  # oförändrat


def test_relay_strict_validation():
    assert local_relay.is_local_id(LOCAL_ID)
    assert local_relay.is_local_id("local:llama3.2:3b-instruct-q4_K_M")
    assert not local_relay.is_local_id("local:")            # tom modell
    assert not local_relay.is_local_id("local:bad model!")  # ogiltiga tecken
    assert not local_relay.is_local_id("step-3.7-flash")
    assert not local_relay.is_local_id("local:" + "x" * 81)  # för långt
    assert local_relay.ollama_model(LOCAL_ID) == "qwen3:14b"


def test_call_llm_hard_rejects_local():
    """Servern måste ALDRIG anropa ett local:-id (defence-in-depth)."""
    for fn, kw in (
        (_ORIG_CALL_LLM, {}),
        (_ORIG_CALL_LLM_REASONING, {}),
    ):
        with pytest.raises(main.HTTPException) as ei:
            asyncio.run(fn(LOCAL_ID, [{"role": "user", "content": "hi"}], **kw))
        assert ei.value.status_code == 500
        assert "local model routed to relay" in str(ei.value.detail)

    async def drain():
        async for _ in _ORIG_STREAM_LLM(LOCAL_ID, [{"role": "user", "content": "hi"}]):
            pass

    with pytest.raises(main.HTTPException) as ei:
        asyncio.run(drain())
    assert ei.value.status_code == 500


# ── prepare ─────────────────────────────────────────────────────────────

def test_prepare_happy_path_contract_shape(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"step_id", "kind", "ollama", "deadline"}
    assert body["kind"] == "generate"
    assert isinstance(body["step_id"], str) and len(body["step_id"]) >= 16
    oll = body["ollama"]
    assert oll["model"] == "qwen3:14b"  # prefixet avskalat
    assert isinstance(oll["messages"], list) and oll["messages"][0]["role"] == "system"
    assert oll["messages"][-1] == {"role": "user", "content": "Jag tittar mig omkring"}
    opts = oll["options"]
    assert opts["num_ctx"] == 16384       # default (Ollamas 4k räcker INTE)
    assert opts["temperature"] == 0.8
    assert opts["num_predict"] == 8192    # inte long-form
    assert body["deadline"] > time.time()


def test_prepare_num_ctx_and_long_form(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok, message="berätta min bakgrundshistoria så långt du kan", num_ctx=32768)
    assert r.status_code == 200, r.text
    opts = r.json()["ollama"]["options"]
    assert opts["num_ctx"] == 32768
    assert opts["num_predict"] == 16000  # long-form → höjd budget
    # out-of-range clampas
    r2 = _prepare(client, tok, message="hej", num_ctx=99)
    assert r2.json()["ollama"]["options"]["num_ctx"] == 2048


def test_prepare_rejects_non_local_and_garbage(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok, model_id="step-3.7-flash")
    assert r.status_code == 400, r.text
    r = _prepare(client, tok, model_id="local:bad model!")
    assert r.status_code == 400, r.text


def test_prepare_auth_and_campaign_errors(client):
    r = client.post("/api/chat/local/prepare", json={"message": "hej", "model_id": LOCAL_ID})
    assert r.status_code == 401
    tok = _seed_player()
    r = _prepare(client, tok)  # ingen kampanj
    assert r.status_code == 404


def test_prepare_disabled_flag_503(client, monkeypatch):
    monkeypatch.setenv("LOCAL_AI_ENABLED", "0")
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok)
    assert r.status_code == 503


# ── commit ──────────────────────────────────────────────────────────────

def test_commit_happy_path_shape_ledger_zero_turns(client):
    tok = _seed_player()
    _make_campaign("alice")
    before = main.load_users()["alice"]["turns_used"]
    r = _prepare(client, tok)
    assert r.status_code == 200, r.text
    step = r.json()["step_id"]
    rc = _commit(client, tok, step, content="Du står vid brunnen. [KAST: 1d20 | Smyga]", tokens=123)
    assert rc.status_code == 200, rc.text
    body = rc.json()
    # EXAKT samma nycklor som /api/chat (kontrakt mot frontend)
    assert set(body) == {
        "reply", "reasoning", "model_id", "tokens", "response_time", "turn_count",
        "summary_generated", "new_npcs", "roll_requests", "ascii_art", "art_type",
        "effects", "guardian_summary", "guardian_pending", "world",
    }
    assert "brunnen" in body["reply"]
    assert "[KAST:" not in body["reply"]
    assert body["roll_requests"] == [{"notation": "1d20", "label": "Smyga"}]
    assert body["model_id"] == LOCAL_ID
    assert body["turn_count"] == 1
    # default-state saknar world.day → fallback 0 (oförändrat hus-beteende)
    assert "day" in body["world"]
    # transkriptet: user + assistant sparade (transcript filen, ej state-dict)
    st = main.store.get("alice")
    entries = main.store.load_transcript(st, last_n=10)
    roles = [e.get("role") for e in entries]
    assert "user" in roles and "assistant" in roles
    a = [e for e in entries if e.get("role") == "assistant"][-1]
    assert a.get("meta", {}).get("model") == LOCAL_ID
    # local_dm-ledgerrad, 0 turns — turns_used ORÖRD
    assert main.load_users()["alice"]["turns_used"] == before
    ledger = main._read_turn_ledger("alice")
    rows = [rec for rec in ledger if rec.get("action") == "local_dm"]
    assert len(rows) == 1
    assert rows[0]["model"] == LOCAL_ID
    assert rows[0]["tokens"] == 123


def test_commit_sok_tag_stripped_without_house_call(client):
    """[SÖK:] i ett relä-svar: minnet hämtas server-side; mockat tomt minne →
    taggen rensas, inget LLM-anrop, ingen turn."""
    tok = _seed_player()
    _make_campaign("alice")
    before = main.load_users()["alice"]["turns_used"]
    step = _prepare(client, tok).json()["step_id"]
    rc = _commit(client, tok, step, content="Något glimtar till. [SÖK: gamla minnen]")
    assert rc.status_code == 200, rc.text
    assert "SÖK" not in rc.json()["reply"]
    assert main.load_users()["alice"]["turns_used"] == before


def test_commit_one_shot_second_use_410(client):
    tok = _seed_player()
    _make_campaign("alice")
    step = _prepare(client, tok).json()["step_id"]
    assert _commit(client, tok, step).status_code == 200
    r = _commit(client, tok, step)
    assert r.status_code == 410


def test_commit_unknown_step_410(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = _commit(client, tok, "nonexistent-step-id")
    assert r.status_code == 410


def test_commit_ttl_expiry_410(client):
    tok = _seed_player()
    _make_campaign("alice")
    step = _prepare(client, tok).json()["step_id"]
    # spola steget förbi TTL (ingen sömn i tester)
    with local_relay._steps_lock:
        local_relay._steps[step]["created_ts"] -= local_relay.ttl_seconds() + 5
    r = _commit(client, tok, step)
    assert r.status_code == 410
    assert step not in local_relay._steps  # förfallet steg släpps aldrig igen


def test_commit_ttl_env_override(client, monkeypatch):
    monkeypatch.setenv("LOCAL_STEP_TTL_SECONDS", "45")
    assert local_relay.ttl_seconds() == 45
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok)
    body = r.json()
    assert 40 < body["deadline"] - time.time() <= 46
    with local_relay._steps_lock:
        local_relay._steps[body["step_id"]]["created_ts"] -= 50
    assert _commit(client, tok, body["step_id"]).status_code == 410


def test_commit_turn_drift_409(client):
    tok = _seed_player()
    _make_campaign("alice")
    step = _prepare(client, tok).json()["step_id"]
    # en "annan flik" hinner chatta före commit → turn_count flyttad
    st = main.store.get("alice")
    st["meta"]["turn_count"] = st["meta"].get("turn_count", 0) + 1
    main.store.save(st)
    r = _commit(client, tok, step)
    assert r.status_code == 409
    # steget är konsumerat (engångs) — klienten måste köa om via ny prepare
    assert _commit(client, tok, step).status_code == 410


def test_commit_foreign_owner_403(client):
    tok_a = _seed_player("alice")
    _make_campaign("alice")
    tok_b = main.load_users()
    users = main.load_users()
    users["bob"] = {"password_hash": hash_password("secret123"), "role": "player",
                    "turn_cap": 50, "turns_used": 0, "subscription_status": "free"}
    main.save_users(users)
    tok_b = create_token("bob", "player")
    _make_campaign_b = main.store.create("bob", name="Bob Campaign", language="en")
    step = _prepare(client, tok_a).json()["step_id"]
    # bob gissar alice steg-id → 403, steget lever kvar (oförgiftat pop)
    r = _commit(client, tok_b, step)
    assert r.status_code == 403
    assert step in local_relay._steps
    # alice kan fortfarande committa det
    assert _commit(client, tok_a, step).status_code == 200


def test_commit_empty_content_400(client):
    tok = _seed_player()
    _make_campaign("alice")
    step = _prepare(client, tok).json()["step_id"]
    r = _commit(client, tok, step, content="   ")
    assert r.status_code == 400
    # steget lever fortfarande (400 prövas FÖRE take) — retrybart inom TTL
    assert _commit(client, tok, step, content="Okei, nu skriver jag.").status_code == 200


def test_daily_cap_429(client, monkeypatch):
    monkeypatch.setenv("LOCAL_DM_DAILY_CAP", "1")
    tok = _seed_player()
    _make_campaign("alice")
    step = _prepare(client, tok).json()["step_id"]
    assert _commit(client, tok, step).status_code == 200
    # andra draget samma dygn → cap nådd (redan i prepare)
    r = _prepare(client, tok)
    assert r.status_code == 429, r.text
    # hus-vägen påverkas INTE av local-capet
    rc = client.post("/api/chat", json={"message": "hej", "model_id": "step-3.7-flash"},
                     cookies={"morkrets_token": tok})
    assert rc.status_code == 200, rc.text


def test_step_store_eviction_cap(client):
    for i in range(local_relay.MAX_STEPS + 25):
        local_relay.stash_step(f"sid-{i}", {"username": "x", "campaign_id": "c",
                                            "turn_count_at_prepare": 0, "model_id": LOCAL_ID,
                                            "message": "m", "ctx": {}, "created_ts": time.time()})
    assert len(local_relay._steps) <= local_relay.MAX_STEPS


def test_dm_model_patch_persists_local(client):
    """clamp + validate gör att PATCH /api/campaign/dm-model accepterar local:*
    automatiskt (free tier) — huset kostar 0 för DM-steget, ingen 10€-gate."""
    tok = _seed_player()
    _make_campaign("alice")
    r = client.patch("/api/campaign/dm-model", json={"dm_model": LOCAL_ID},
                     cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["dm_model"] == LOCAL_ID
