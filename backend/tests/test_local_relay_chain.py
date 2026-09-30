"""🏮 Local AI v2 — 'Whole Cauldron local' klientkedja (rollcheck → dm →
repair? → guardian → extract → search?).

Kontrakt (frysett, vault dnd-llm-local-ollama-impl-2026-09 §1a):
  - PATCH /api/campaign/local-pipeline {"pipeline":"dm"|"full"} →
    {ok:true, pipeline}; "full" kräver local:* dm_model; tom meta = "dm".
  - full-mode prepare → rollcheck-hop (json, temp 0.1, num_predict 1024);
    vaknande/[Resultat:] → dm-hop direkt (temp 0.8, ingen format).
  - commit dispatchar på stegets `chain`; varje commit → nästa generate-steg
    eller EXAKT hus-JSON-shapen (done). local_dm-bokföring EXAKT en rad per
    drag (på dm-commiten). state sparas på dm-commiten → avbrott = giltigt
    drag utan anrikning.
  - cap: LOCAL_DM_DAILY_CAP (100) dm / LOCAL_DM_DAILY_CAP_FULL (300) full —
    räknas från SAMMA local_dm-rader.
  - husets _call_llm får ALDRIG anropas för carved-roller i full mode
    (assert via spy); bg-tasks registreras exakt en gång (dm-commiten).

Fixtures: samma mönster som test_local_relay.py — ALLTID tmp-data
(conftest redirectar ledgers/grants; users/campaigns här).
"""
import json
import sys
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

LOCAL_ID = "local:qwen3:14b"
HOUSE_KEYS = {
    "reply", "reasoning", "model_id", "tokens", "response_time", "turn_count",
    "summary_generated", "new_npcs", "roll_requests", "ascii_art", "art_type",
    "effects", "guardian_summary", "guardian_pending", "world",
}


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
    # extraction.py har en MODUL-NIVÅ-kopia — FactRegister (extract-commiten)
    # får ALDRIG skriva till riktig backend/data
    import extraction
    monkeypatch.setattr(extraction, "_CAMPAIGNS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def llm_spy(monkeypatch):
    """Ingen riktig nätverks-LLM. Spy: loggar alla main._call_llm-anrop —
    kedjan får ALDRIG röda hus-modeller för carved-roller, men bakgrunds-
    uppgifter (summaries, threads) får (de är medvetet house-side)."""
    calls: list[tuple[str, str]] = []

    async def fake_dm(model_id, messages, **kw):
        return ("The wind howls.", "n/a", {"total_tokens": 1})

    async def spy_call_llm(model_id, messages, **kw):
        calls.append((str(model_id), "call_llm"))
        return "OK"

    async def noop(*a, **k):
        return None

    async def noop_guardian_post(*a, **k):
        return None

    async def noop_post_turn_tasks(*a, **k):
        return None

    async def no_memory(*a, **k):
        return {"text": "", "facts_sent": 0, "rag_sent": 0, "timing_s": 0.0}

    monkeypatch.setattr(main, "_call_llm_with_reasoning", fake_dm)
    monkeypatch.setattr(main, "_call_llm", spy_call_llm)
    monkeypatch.setattr(main, "guardian_check_roll", noop)
    monkeypatch.setattr(main, "_retrieve_relevant_memory", no_memory)
    # hus-bakgrunder noop:as med NAMNGIVNA koroutiner — no_bg klassificerar
    # registrerade coros via cr_code.co_name
    monkeypatch.setattr(main, "_guardian_post_dm", noop_guardian_post)
    monkeypatch.setattr(main, "_post_turn_tasks", noop_post_turn_tasks)
    return calls


@pytest.fixture(autouse=True)
def local_env(monkeypatch):
    monkeypatch.setenv("LOCAL_AI_ENABLED", "1")
    monkeypatch.delenv("LOCAL_STEP_TTL_SECONDS", raising=False)
    monkeypatch.delenv("LOCAL_DM_DAILY_CAP", raising=False)
    monkeypatch.delenv("LOCAL_DM_DAILY_CAP_FULL", raising=False)
    local_relay.clear_steps()
    yield
    local_relay.clear_steps()


@pytest.fixture(autouse=True)
def no_bg(monkeypatch):
    """_register_bg_task räknar men spawnar inga tasks (TestClient-eventloop-
    osäkerhet); klassificering via cr_code.co_name (noop-namnen i llm_spy)."""
    counts: dict[str, int] = {"guardian": 0, "post": 0, "other": 0, "total": 0}

    class DummyTask:
        def add_done_callback(self, cb):
            pass

    def fake_register(username, campaign_id, coro):
        try:
            coro.close()
        except Exception:
            pass
        name = getattr(getattr(coro, "cr_code", None), "co_name", "") or ""
        counts["total"] += 1
        if "guardian" in name:
            counts["guardian"] += 1
        elif "post_turn" in name:
            counts["post"] += 1
        else:
            counts["other"] += 1
        return DummyTask()

    monkeypatch.setattr(main, "_register_bg_task", fake_register)
    return counts


@pytest.fixture
def client(users_file, campaigns_dir, llm_spy):
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
    main.store.create(username, name="Chain Test Campaign", language="en")


def _set_pipeline(client, tok, pipeline):
    return client.patch("/api/campaign/local-pipeline",
                        json={"pipeline": pipeline},
                        cookies={"morkrets_token": tok})


def _set_dm_model(client, tok, model_id):
    return client.patch("/api/campaign/dm-model", json={"dm_model": model_id},
                        cookies={"morkrets_token": tok})


def _prepare(client, tok, message="I look around", model_id=LOCAL_ID, **kw):
    body = {"message": message, "model_id": model_id}
    body.update(kw)
    return client.post("/api/chat/local/prepare", json=body,
                       cookies={"morkrets_token": tok})


def _commit(client, tok, step_id, content="You stand on a hill. The wind howls.", **kw):
    body = {"step_id": step_id, "content": content}
    body.update(kw)
    return client.post("/api/chat/local/commit", json=body,
                       cookies={"morkrets_token": tok})


def _go_full(client, tok):
    """local dm_model + pipeline 'full' — standard-förfarandet."""
    r = _set_dm_model(client, tok, LOCAL_ID)
    assert r.status_code == 200, r.text
    r = _set_pipeline(client, tok, "full")
    assert r.status_code == 200, r.text
    return r.json()


def _drain_chain(client, tok, step_body, dm_content, roll_needs=False,
                 guardian_json=None, extract_json=None, search_final=None):
    """Kör kedjan till done från (och med) det första steget `step_body`.
    Returnerar listan av steg-typer + done-body."""
    seen = []
    body = step_body
    while body.get("kind") == "generate":
        chain = body["chain"]
        seen.append(chain)
        if chain == "rollcheck":
            content = (json.dumps({"needs_roll": True, "notation": "1d20 + DEX",
                                   "label": "Sneak", "skill": "Stealth"})
                       if roll_needs else json.dumps({"needs_roll": False}))
        elif chain == "dm":
            content = dm_content
        elif chain == "repair":
            content = search_final or dm_content
        elif chain == "guardian":
            content = guardian_json if guardian_json is not None else "{}"
        elif chain == "extract":
            content = extract_json if extract_json is not None else json.dumps(
                {"facts": [], "inventory_changes": []})
        elif chain == "search":
            content = search_final or "Final narrated reply with memory woven in."
        else:
            raise AssertionError(f"okänd chain: {chain}")
        r = _commit(client, tok, body["step_id"], content=content)
        assert r.status_code == 200, (chain, r.text)
        body = r.json()
    assert "reply" in body, body
    return seen, body


# ── pipeline-PATCH ─────────────────────────────────────────────────────

def test_pipeline_patch_flips_meta_and_validates(client):
    tok = _seed_player()
    _make_campaign("alice")
    # hus-dm_model ⇒ "full" nekas
    r = _set_pipeline(client, tok, "full")
    assert r.status_code == 400, r.text
    st = main.store.get("alice")
    assert st["meta"].get("local_pipeline") is None  # tom meta = dm
    # "dm" tillåts alltid
    r = _set_pipeline(client, tok, "dm")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "pipeline": "dm"}
    assert main.store.get("alice")["meta"]["local_pipeline"] == "dm"
    # lokal dm_model ⇒ "full" accepteras
    r = _set_dm_model(client, tok, LOCAL_ID)
    assert r.status_code == 200, r.text
    r = _set_pipeline(client, tok, "full")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "pipeline": "full"}
    assert main.store.get("alice")["meta"]["local_pipeline"] == "full"
    # ogiltigt värde
    r = _set_pipeline(client, tok, "banana")
    assert r.status_code == 400


def test_pipeline_patch_requires_auth(client):
    r = _set_pipeline(client, "garbage", "dm")
    assert r.status_code == 401


# ── prepare i full mode ────────────────────────────────────────────────

def test_full_prepare_returns_rollcheck_hop(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    r = _prepare(client, tok, message="I sneak toward the gate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "generate" and body["chain"] == "rollcheck"
    opts = body["ollama"]["options"]
    assert opts["format"] == "json"
    assert opts["temperature"] == 0.1
    assert opts["num_predict"] == 1024
    assert opts["num_ctx"] == 16384  # clampat default, som v1
    msgs = body["ollama"]["messages"]
    assert msgs[0]["role"] == "system" and "dice" in msgs[1]["content"].lower()
    assert body["ollama"]["model"] == "qwen3:14b"


def test_full_prepare_awakening_returns_dm_hop_directly(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    r = _prepare(client, tok, message="__VAKNA_DM__")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "dm"
    opts = body["ollama"]["options"]
    assert opts["temperature"] == 0.8
    assert "format" not in opts          # exakt som v1-dm-hopp
    assert opts["num_predict"] == 8192


def test_full_prepare_resultat_returns_dm_hop_directly(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    r = _prepare(client, tok, message="[Resultat: Stealth → 14]")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "dm"
    assert "format" not in body["ollama"]["options"]


def test_dm_mode_prepare_unchanged_no_chain(client):
    """v1 dm-läge: svaret har ALDRIG en chain-nyckel (byte-identiskt kontrakt)."""
    tok = _seed_player()
    _make_campaign("alice")
    r = _prepare(client, tok)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "chain" not in body
    assert set(body) == {"step_id", "kind", "ollama", "deadline"}


# ── rollcheck → dm ─────────────────────────────────────────────────────

def test_rollcheck_commit_returns_dm_hop(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    assert step["chain"] == "rollcheck"
    r = _commit(client, tok, step["step_id"],
                content=json.dumps({"needs_roll": True, "notation": "1d20 + DEX",
                                    "label": "Sneak", "skill": "Stealth"}))
    assert r.status_code == 200, r.text
    dm_hop = r.json()
    assert dm_hop["chain"] == "dm"
    assert dm_hop["ollama"]["options"]["temperature"] == 0.8
    assert "format" not in dm_hop["ollama"]["options"]
    # guardian-rådet vevas in i DM-prompten (fas A2 med guardian_roll)
    sys_txt = dm_hop["ollama"]["messages"][0]["content"]
    assert "Sneak" in sys_txt or "1d20 + DEX" in sys_txt
    # ingen local_dm-rad ännu — bokfirs på dm-commiten
    assert [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"] == []


def test_rollcheck_invalid_json_treated_as_no_roll(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    r = _commit(client, tok, step["step_id"], content="this is not json")
    assert r.status_code == 200, r.text
    assert r.json()["chain"] == "dm"


# ── dm-commit: bokföring, state, bg-registrering ───────────────────────

def test_dm_commit_books_one_ledger_row_and_saves_state(client):
    """dm-hoppets commit: EXAKT en local_dm-rad, turnen sparad, turns_used
    orörd — och avbrott här lämnar ett giltigt läge (testas vidare i
    test_guardian_done_pending_contract_on_abandon)."""
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    before = main.load_users()["alice"]["turns_used"]
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    r = _commit(client, tok, dm_hop["step_id"], content="You wait at the crossroads.",
                tokens=42)
    assert r.status_code == 200, r.text
    guardian_step = r.json()
    assert guardian_step["chain"] == "guardian"
    rows = [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"]
    assert len(rows) == 1
    assert rows[0]["model"] == LOCAL_ID and rows[0]["tokens"] == 42
    assert main.load_users()["alice"]["turns_used"] == before
    st = main.store.get("alice")
    assert st["meta"]["turn_count"] == 1
    roles = [e.get("role") for e in main.store.load_transcript(st, last_n=10)]
    assert roles == ["user", "assistant"]


def test_full_chain_dm_commit_then_guardian_extract_done(client, llm_spy, no_bg):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    before = main.load_users()["alice"]["turns_used"]
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": True, "notation": "1d20",
                                         "label": "Perception", "skill": ""})).json()
    assert dm_hop["chain"] == "dm"
    # dm-commit → guardian-hop (vald mekanik giltig → ingen repair; turn 1 ⇒
    # extract varannan tur = UTSKUTEN; inget [SÖK:] ⇒ done direkt? nej:
    # guardian kommer alltid först i kön)
    g = _commit(client, tok, dm_hop["step_id"],
                content="You stand at the gate. [KAST: 1d20 | Sneak]", tokens=77)
    assert g.status_code == 200, g.text
    guardian_step = g.json()
    assert guardian_step["chain"] == "guardian"
    opts = guardian_step["ollama"]["options"]
    assert opts["format"] == "json" and opts["temperature"] == 0.1
    # turnen är REDAN sparad (avbrott-säkerhet): user+assistant i transkript,
    # local_dm-rad EXAKT en, turns_used orörd
    st = main.store.get("alice")
    assert st["meta"]["turn_count"] == 1
    rows = [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"]
    assert len(rows) == 1 and rows[0]["model"] == LOCAL_ID and rows[0]["tokens"] == 77
    assert main.load_users()["alice"]["turns_used"] == before
    entries = main.store.load_transcript(st, last_n=10)
    assert [e.get("role") for e in entries] == ["user", "assistant"]
    # guardian commit → done (turn 1 udda ⇒ extract utskutet)
    d = _commit(client, tok, guardian_step["step_id"],
                content=json.dumps({"damage": [], "xp": 0, "logbook": ""}))
    assert d.status_code == 200, d.text
    done = d.json()
    assert set(done) == HOUSE_KEYS
    assert done["guardian_pending"] is False  # guardian applicerad & klar
    assert done["model_id"] == LOCAL_ID
    assert done["turn_count"] == 1
    # inga hus-_call_llm-anrop för carved-roller + bg registrerat exakt en gång
    assert llm_spy == []
    assert no_bg["guardian"] == 0  # hus-Guardian INTE registrerad i full mode
    assert no_bg["post"] == 1      # övriga hus-bg-jobb EN gång (dm-commiten)


def test_full_chain_turn2_includes_extract_hop(client, campaigns_dir):
    """Andra dragen (turn_count==2 jämn) ⇒ extract-hop i kön efter guardian."""
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    # turn 1
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    g = _commit(client, tok, dm_hop["step_id"], content="The road stretches on.").json()
    assert g["chain"] == "guardian"
    d = _commit(client, tok, g["step_id"], content="{}").json()
    assert set(d) == HOUSE_KEYS  # turn 1 udda ⇒ ingen extract
    # turn 2 ⇒ extractDue (turn_count blir 2)
    step2 = _prepare(client, tok).json()
    dm2 = _commit(client, tok, step2["step_id"],
                  content=json.dumps({"needs_roll": False})).json()
    g2 = _commit(client, tok, dm2["step_id"], content="You meet a merchant.").json()
    assert g2["chain"] == "guardian"
    e = _commit(client, tok, g2["step_id"],
                content=json.dumps({"healing": [{"target": "player", "amount": 1}]})).json()
    assert e["chain"] == "extract"
    assert e["ollama"]["options"]["format"] == "json"
    d2 = _commit(client, tok, e["step_id"], content=json.dumps(
        {"facts": [{"category": "event", "text": "Met a merchant at the crossroads",
                    "confidence": 0.9}],
         "inventory_changes": []})).json()
    assert set(d2) == HOUSE_KEYS
    assert d2["turn_count"] == 2
    # fakten arkiverades via FactRegister (delad house-apply)
    reg = main.FactRegister("alice", main.store.get("alice")["meta"]["campaign_id"])
    assert any("merchant" in f.text.lower() for f in reg._facts)


def test_guardian_done_pending_contract_on_abandon(client):
    """Avbrott EFTER dm-commit: draget står, nästa drag fungerar, och en
    senare kedja är inte blockerad. Done-JSON vid genomförd guardian ⇒ False;
    annars håller vi True (klienten pollar transkriptet som idag)."""
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    # abandon: committa aldrig guardian-steget
    _commit(client, tok, dm_hop["step_id"], content="A half told tale. [KAST: 1d20 | Watch]")
    # nästa drag fungerar (turn-drift tillåten ⇒ ny prepare/commit)
    step2 = _prepare(client, tok).json()
    assert step2["chain"] == "rollcheck"
    dm2 = _commit(client, tok, step2["step_id"],
                  content=json.dumps({"needs_roll": False})).json()
    g2 = _commit(client, tok, dm2["step_id"], content="The tale continues.").json()
    nxt = _commit(client, tok, g2["step_id"], content="{}").json()
    if nxt.get("chain") == "extract":  # turn 2 jamn ⇒ extraktion ar aktuell
        nxt = _commit(client, tok, nxt["step_id"],
                      content=json.dumps({"facts": [], "inventory_changes": []})).json()
    d = nxt
    assert d["guardian_pending"] is False
    assert d["turn_count"] == 2
    rows = [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"]
    assert len(rows) == 2


# ── repair-hop ─────────────────────────────────────────────────────────

def test_invalid_mechanics_produce_repair_hop(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    # [SKADA:999] ⇒ valideringsfel (skar overskrider max-HP)
    g = _commit(client, tok, dm_hop["step_id"], content="The dragon breathes! [SKADA:999]")
    assert g.status_code == 200, g.text
    rep = g.json()
    assert rep["chain"] == "repair"
    assert rep["ollama"]["options"]["temperature"] == 0.8
    assert rep["ollama"]["options"]["num_predict"] == 8192
    msgs = rep["ollama"]["messages"]
    assert msgs[-1]["content"].startswith("Ditt förra svar hade dessa fel")
    assert msgs[-2]["content"] == "The dragon breathes! [SKADA:999]"
    # reparera → giltigt → guardian → done
    g2 = _commit(client, tok, rep["step_id"], content="A lucky roll aside, the beast misses.").json()
    assert g2["chain"] == "guardian"
    d = _commit(client, tok, g2["step_id"], content="{}").json()
    assert set(d) == HOUSE_KEYS
    # reparerad svaret ar nu den giltiga narrationen (mekanik OK)
    assert "misses" in d["reply"]


def test_repair_still_invalid_discards_mechanics(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    rep = _commit(client, tok, dm_hop["step_id"], content="Nope [SKADA:999]").json()
    assert rep["chain"] == "repair"
    # andra försöket fortfarande trasigt → förkasta mekanik, behåll narration
    g = _commit(client, tok, rep["step_id"], content="Still bad [SKADA:9999]")
    assert g.status_code == 200, g.text
    assert g.json()["chain"] == "guardian"
    d = _commit(client, tok, g.json()["step_id"], content="{}").json()
    assert d["effects"] == []
    assert "[SKADA:" not in d["reply"]
    assert "Still bad" in d["reply"]
    # EXAKT en local_dm-rad trots repair
    rows = [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"]
    assert len(rows) == 1


# ── search-hop ─────────────────────────────────────────────────────────

def test_search_hop_replaces_final_reply(client, monkeypatch):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)

    async def mem_with_text(username, campaign_id, query, state):
        return {"text": f"MEMORY about {query}", "facts_sent": 1, "rag_sent": 1, "timing_s": 0.1}

    monkeypatch.setattr(main, "_retrieve_relevant_memory", mem_with_text)
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    g = _commit(client, tok, dm_hop["step_id"],
                content="Something glimmers. [SÖK: old letters]").json()
    assert g["chain"] == "guardian"
    # search kommer INTE ut före guardian/extract; turn 1 ⇒ extract skuten
    d = _commit(client, tok, g["step_id"], content="{}")
    assert d.status_code == 200, d.text
    body = d.json()
    if body.get("chain") == "search":
        s = body
    else:
        pytest.fail(f"search-hop väntad, fick {set(body)}")
    assert "[SÖK" not in (s["ollama"]["messages"][-2]["content"])  # tag stripped på dm-svar
    assert "MEMORY about old letters" in s["ollama"]["messages"][-1]["content"]
    f = _commit(client, tok, s["step_id"],
                content="The letters speak of the vault. [KAST: 1d20 | Search]").json()
    assert set(f) == HOUSE_KEYS
    assert "vault" in f["reply"]
    assert "[SÖK" not in f["reply"]
    assert f["guardian_pending"] is False


# ── cap ────────────────────────────────────────────────────────────────

def test_full_cap_300_vs_dm_cap_100_same_rows(monkeypatch):
    assert local_relay.daily_cap("dm") == 100
    assert local_relay.daily_cap("full") == 300
    monkeypatch.setenv("LOCAL_DM_DAILY_CAP", "1")
    monkeypatch.setenv("LOCAL_DM_DAILY_CAP_FULL", "2")
    assert local_relay.daily_cap("dm") == 1
    assert local_relay.daily_cap("full") == 2
    # räknas från SAMMA local_dm-rader
    main._append_turn_ledger("carol", "local_dm", LOCAL_ID, 0)
    assert local_relay.local_dm_count_today("carol") == 1
    assert not local_relay.under_daily_cap("carol", "dm")
    assert local_relay.under_daily_cap("carol", "full")


def test_full_cap_enforced_via_endpoint(client, monkeypatch):
    monkeypatch.setenv("LOCAL_DM_DAILY_CAP_FULL", "1")
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step["step_id"],
                     content=json.dumps({"needs_roll": False})).json()
    g = _commit(client, tok, dm_hop["step_id"], content="Done tale.").json()
    _commit(client, tok, g["step_id"], content="{}")
    # andra draget ⇒ 429 redan i prepare (cap läses med pipeline=full)
    r = _prepare(client, tok)
    assert r.status_code == 429, r.text
    assert "1" in r.json()["detail"]


# ── hop-häntering: engångssteg, ägarskap, 409 ─────────────────────────

def test_chain_steps_one_shot_and_drift_409(client):
    tok = _seed_player()
    _make_campaign("alice")
    _go_full(client, tok)
    step = _prepare(client, tok).json()
    sid = step["step_id"]
    assert _commit(client, tok, sid, content="{}").status_code == 200
    assert _commit(client, tok, sid, content="{}").status_code == 410
    # turn-drift på ett dm-steg ⇒ 409 + snapshot-discarded, ingen bokföring
    step2 = _prepare(client, tok).json()
    dm_hop = _commit(client, tok, step2["step_id"], content="{}").json()
    st = main.store.get("alice")
    st["meta"]["turn_count"] += 1
    main.store.save(st)
    r = _commit(client, tok, dm_hop["step_id"], content="too late")
    assert r.status_code == 409, r.text
    rows = [x for x in main._read_turn_ledger("alice") if x["action"] == "local_dm"]
    assert len(rows) == 0  # inget av det avbrutna bokfördes
