"""OpenRouter free-modeller (orfree:) i modellväljarna.

2026-09-27 (ny prissättning): orfree: ligger bakom 10€-unlåset — free/tier1
klampas till DEFAULT_PLAYER_MODEL; tier2/lifetime/admin behåller orfree:.

Täcker:
  - _clamp_player_model tillåter kända orfree: för tier2/lifetime/None
  - free/tier1 → default; okända orfree: → default (safe)
  - PATCH /api/campaign/dm-model (och guardian/extraction) accepterar orfree:
  - create_campaign sparar extraction_model=orfree:...
  - _extraction_model_for returnerar orfree: oförändrad (ingen get_model-validering)
  - _stream_llm delegerar orfree: till or_free.chat_free_stream (karaktärsskapande)

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger mot tmp —
ALDRIG riktig data.
"""
import asyncio
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

KNOWN = "orfree:openai/gpt-oss-20b:free"


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


@pytest.fixture
def client(users_file, campaigns_dir, llm_mocks):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed_player(username="alice", role="player", status="free", unlocked=False):
    """Skapa spelaren direkt i users.json (undviker registrerings-rate-limitern
    _REGISTER_TIMES som är process-global och inte resets mellan tester).

    unlocked=True → 10€-unlås (features.all_models utan utgångsdatum →
    _tier_for = tier2 permanent, samma form som unlock10-webhooken sätter).
    2026-09-27: orfree: kräver unlock — free/tier1 klampas till default."""
    users = main.load_users()
    u = {
        "password_hash": hash_password("secret123"),
        "role": role,
        "turn_cap": 50,
        "turns_used": 0,
        "turn_bonus": 0,
        "promo_bonus": 0,
        "subscription_status": status,
    }
    if unlocked:
        u["features"] = {"all_models": True, "export": True, "wan1080": True, "unlock10": True}
        u["features_until"] = None
    users[username] = u
    main.save_users(users)
    return create_token(username, role)


def _user(username="alice") -> dict:
    return main.load_users().get(username, {})


def _make_campaign(username):
    main.store.create(username, name="Test Campaign", language="en")


def _admin_token():
    users = main.load_users()
    users["the_admin"] = {"password_hash": hash_password("pw123456"), "role": "admin", "turn_cap": 0}
    main.save_users(users)
    return create_token("the_admin", "admin")


# ── Clamp (alla tiers) ──────────────────────────────────────────────────

def test_clamp_allows_known_orfree_for_unlocked_tiers():
    """2026-09-27: orfree: bakom 10€-unlåset — tier2/lifetime/None (interna
    anrop) behåller valet; free/tier1 klampas till default."""
    for tier in ("tier2", "lifetime", None):
        assert main._clamp_player_model(KNOWN, tier=tier) == KNOWN, tier
    for tier in ("free", "tier1"):
        assert main._clamp_player_model(KNOWN, tier=tier) == main.DEFAULT_PLAYER_MODEL, tier


def test_clamp_rejects_unknown_orfree_to_default():
    for tier in ("free", "tier1", "tier2"):
        assert main._clamp_player_model("orfree:evil/not-real:free", tier=tier) == main.DEFAULT_PLAYER_MODEL


# ── PATCH-endpoints (icke-admin) ────────────────────────────────────────

def test_non_admin_can_set_dm_orfree(client):
    """Unlocked (10€) icke-admin kan välja orfree: som DM."""
    tok = _seed_player(unlocked=True)
    _make_campaign("alice")
    r = client.patch("/api/campaign/dm-model", json={"dm_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["dm_model"] == KNOWN


def test_non_admin_can_set_guardian_orfree(client):
    tok = _seed_player(unlocked=True)
    _make_campaign("alice")
    r = client.patch("/api/campaign/guardian-model", json={"guardian_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["guardian_model"] == KNOWN


def test_non_admin_can_set_extraction_orfree(client):
    tok = _seed_player(unlocked=True)
    _make_campaign("alice")
    r = client.patch("/api/campaign/extraction-model", json={"extraction_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["extraction_model"] == KNOWN


def test_non_admin_unknown_orfree_clamped_to_default(client):
    """Okänd orfree: klampas till default ÄVEN för unlocked-spelare."""
    tok = _seed_player(unlocked=True)
    _make_campaign("alice")
    r = client.patch("/api/campaign/dm-model", json={"dm_model": "orfree:evil/not-real:free"},
                     cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["dm_model"] == main.DEFAULT_PLAYER_MODEL


def test_admin_unknown_orfree_rejected(client):
    tok = _seed_player("the_admin", role="admin")
    main.store.create("the_admin", name="Admin Campaign", language="en")
    r = client.patch("/api/campaign/dm-model", json={"dm_model": "orfree:evil/not-real:free"},
                     cookies={"morkrets_token": tok})
    assert r.status_code == 400, r.text


# ── create_campaign + extraction-model ──────────────────────────────────

def test_create_campaign_saves_orfree_extraction(client):
    tok = _seed_player(unlocked=True)
    r = client.post("/api/campaign", json={"name": "OR test", "language": "en", "extraction_model": KNOWN},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["extraction_model"] == KNOWN
    # och _extraction_model_for returnerar den oförändrad (ingen get_model-validering)
    assert main._extraction_model_for(st) == KNOWN


# ── _stream_llm-routing (karaktärsskapande med orfree:) ─────────────────

def test_stream_llm_routes_orfree_to_chat_free_stream(monkeypatch):
    """_stream_llm måste delegera orfree: till or_free.chat_free_stream —
    get_model() skulle krascha (orfree: finns inte i MODELS-registret)."""
    import or_free

    seen = {}

    async def fake_stream(model_id, messages, **kw):
        seen["model_id"] = model_id
        seen["kw"] = kw
        yield ("thinking…", "", None)
        yield ("", '{"name":"Testy"}', None)
        yield ("", "", {"total_tokens": 7})

    monkeypatch.setattr(or_free, "chat_free_stream", fake_stream)

    async def run():
        out = []
        async for r, c, u in main._stream_llm(KNOWN, [{"role": "user", "content": "hi"}]):
            out.append((r, c, u))
        return out

    out = asyncio.run(run())
    assert seen["model_id"] == KNOWN
    assert out == [
        ("thinking…", "", None),
        ("", '{"name":"Testy"}', None),
        ("", "", {"total_tokens": 7}),
    ]


def test_vault_generate_stream_accepts_orfree_for_unlocked_player(client, monkeypatch):
    """2026-09-27: unlocked-spelare (10€) genererar karaktär med orfree: —
    hela vägen via _stream_llm → or_free.chat_free_stream (ingen get_model-krasch)."""
    import or_free

    CHAR_JSON = (
        '{"name":"Ashen","race":"Human","class":"Rogue","level":1,'
        '"hp":{"current":10,"max":10},'
        '"abilities":{"STR":{"score":10,"mod":0},"DEX":{"score":14,"mod":2},'
        '"CON":{"score":12,"mod":1},"INT":{"score":10,"mod":0},'
        '"WIS":{"score":10,"mod":0},"CHA":{"score":12,"mod":1}},'
        '"ac":14,"story":"A quiet shadow.","traits":["Stealthy"]}'
    )

    async def fake_stream(model_id, messages, **kw):
        yield ("", CHAR_JSON, None)
        yield ("", "", {"total_tokens": 10})

    monkeypatch.setattr(or_free, "chat_free_stream", fake_stream)

    tok = _seed_player(status="free", unlocked=True)
    r = client.post("/api/vault/generate/stream",
                    json={"prompt": "A rogue", "model_id": KNOWN, "lang": "en"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    assert '"ok":true' in r.text or '"ok": true' in r.text, r.text
    assert '"name":"Ashen"' in r.text or '"name": "Ashen"' in r.text, r.text
    assert '"reasoning_len":0' in r.text or '"reasoning_len": 0' in r.text, r.text
