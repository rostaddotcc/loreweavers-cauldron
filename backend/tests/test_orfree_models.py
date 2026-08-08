"""OpenRouter free-modeller i den ordinarie 3-vals-väljaren (2026-08-08).

Täcker:
  - _clamp_player_model tillåter kända orfree: för ALLA tiers (free/tier1/tier2)
  - okända orfree: klampas till DEFAULT_PLAYER_MODEL (safe default)
  - PATCH /api/campaign/dm-model (och guardian/extraction) accepterar orfree:
  - create_campaign sparar extraction_model=orfree:...
  - _extraction_model_for returnerar orfree: oförändrad (ingen get_model-validering)

autouse-fixtures: ALLA tester pekar users.json + kampanjer + ledger mot tmp —
ALDRIG riktig data.
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


def _seed_player(username="alice", role="player", status="free"):
    """Skapa spelaren direkt i users.json (undviker registrerings-rate-limitern
    _REGISTER_TIMES som är process-global och inte resets mellan tester)."""
    users = main.load_users()
    users[username] = {
        "password_hash": hash_password("secret123"),
        "role": role,
        "turn_cap": 50,
        "turns_used": 0,
        "turn_bonus": 0,
        "promo_bonus": 0,
        "subscription_status": status,
    }
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

def test_clamp_allows_known_orfree_for_all_tiers():
    for tier in ("free", "tier1", "tier2", "lifetime", None):
        assert main._clamp_player_model(KNOWN, tier=tier) == KNOWN, tier


def test_clamp_rejects_unknown_orfree_to_default():
    for tier in ("free", "tier1", "tier2"):
        assert main._clamp_player_model("orfree:evil/not-real:free", tier=tier) == main.DEFAULT_PLAYER_MODEL


# ── PATCH-endpoints (icke-admin) ────────────────────────────────────────

def test_non_admin_can_set_dm_orfree(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = client.patch("/api/campaign/dm-model", json={"dm_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["dm_model"] == KNOWN


def test_non_admin_can_set_guardian_orfree(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = client.patch("/api/campaign/guardian-model", json={"guardian_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["guardian_model"] == KNOWN


def test_non_admin_can_set_extraction_orfree(client):
    tok = _seed_player()
    _make_campaign("alice")
    r = client.patch("/api/campaign/extraction-model", json={"extraction_model": KNOWN}, cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["extraction_model"] == KNOWN


def test_non_admin_unknown_orfree_clamped_to_default(client):
    tok = _seed_player()
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
    tok = _seed_player()
    r = client.post("/api/campaign", json={"name": "OR test", "language": "en", "extraction_model": KNOWN},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    st = main.store.get("alice")
    assert st["meta"]["extraction_model"] == KNOWN
    # och _extraction_model_for returnerar den oförändrad (ingen get_model-validering)
    assert main._extraction_model_for(st) == KNOWN
