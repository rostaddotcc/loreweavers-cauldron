"""Föremålsmålningar (2026-09-30) — item:<slug> som avatar-kind.

Varje inventory-item kan AI-målas utifrån sin egen beskrivning via samma
motor/galleri som karaktärsavataren. Testerna täcker:
  - slug-sanitering + _safe_avatar_key-rejektion av ogiltiga item-kind
  - generering drar 1 turn och sparar bild + galleri-post under item:<slug>
  - prompten byggs ur itemets fält (namn/beskrivning/lore)
  - GET /api/campaign/avatar/item:<slug> returnerar bilden
  - tier-gate: free tier → 403 feature_locked (bildgenerering = 10€-unlås)

autouse-fixtures: ALLA tester pekar users.json + kampanjer mot tmp —
ALDRIG riktig data (samma mönster som test_image_turn_charge.py).
"""
import base64
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


@pytest.fixture(autouse=True)
def fake_stepfun(monkeypatch):
    """Stubba StepFun HTTP-et — ingen riktig API-nyckel/network i tester."""
    class _FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            b64 = base64.b64encode(b"fake-item-image").decode()
            return {"data": [{"b64_json": b64}]}

    async def _fake_post(self, *args, **kwargs):
        return _FakeResp()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setenv("STEPFUN_API_KEY", "test-key")


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, fake_stepfun):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", role="player", features=None):
    u = {"password_hash": hash_password("secret123"), "role": role,
         "turn_cap": 50, "turns_used": 0, "turn_bonus": 0, "promo_bonus": 0,
         "start_bonus_granted": True,
         "reset_date": "2099-01-01", "subscription_status": "free",
         "subscription_until": None,
         "features": features if features is not None else
         {"export": True, "all_models": True, "wan1080": True, "unlock10": True},
         "features_until": None,
         "wan_used_today": 0, "wan_reset_date": None,
         "created_at": "2026-08-01T10:00:00+00:00",
         "last_login": "2026-08-04T09:00:00+00:00"}
    main.save_users({username: u})


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _seed_campaign(username, inventory=None):
    main.store.create(username, name="Test Campaign", language="en")
    if inventory is not None:
        state = main.store.get(username)
        state["inventory"] = inventory
        main.store.save(state)


DAGGER = {
    "name": "Worn Ritual Dagger",
    "type": "Vapen",
    "qty": 1,
    "weight": 1.0,
    "equipped": True,
    "rarity": "magic",
    "description": "A notched obsidian blade with a bone handle, warm to the touch.",
    "lore": "It hums faintly near old blood.",
    "damage_dice": "1d4",
    "damage_type": "piercing",
}


# ── Slug + key-sanitering ──

def test_item_slug_basic():
    assert main._item_slug("Worn Ritual Dagger") == "worn-ritual-dagger"


def test_item_slug_matches_frontend_rules():
    # Samma pipeline som frontendens _itemSlug(): strip → icke-[a-z0-9] → '-',
    # rensa kanter, max 48, ingen trailing '-'.
    assert main._item_slug("  Glazier's  Lamp!! ") == "glazier-s-lamp"
    assert main._item_slug("---") == ""
    long = "x" * 80
    s = main._item_slug(long)
    assert len(s) == 48
    # Trunkering mitt i ett bindestreck får inte lämna trailing '-'
    assert not main._item_slug("ab " + "c" * 60).endswith("-")


def test_safe_avatar_key_accepts_valid_item_kind():
    assert main._safe_avatar_key("item:worn-ritual-dagger") == "item:worn-ritual-dagger"
    assert main._safe_avatar_key("item:a1-b2") == "item:a1-b2"


def test_safe_avatar_key_rejects_bad_item_kinds():
    from fastapi import HTTPException
    for bad in ("item:", "item:UPPER", "item:has space", "item:../evil",
                "item:a--b", "item:-lead", "item:trail-", "item:" + "a" * 60,
                "item:under_score"):
        with pytest.raises(HTTPException):
            main._safe_avatar_key(bad)


# ── Prompt-bygge ──

def test_item_prompt_uses_item_fields():
    state = {"inventory": [DAGGER]}
    p = main._build_avatar_prompt(state, "item:worn-ritual-dagger", seed=1)
    assert "Worn Ritual Dagger" in p
    assert "notched obsidian blade" in p
    assert "hums faintly near old blood" in p
    # Stil + komposition ligger FÖRE beskrivningen (trim klipper bakifrån)
    assert p.index("Photorealistic") < p.index("notched obsidian")
    # Endpointen skickar _trim_prompt(p) — samma kontrakt som karaktärsavataren
    assert len(main._trim_prompt(p)) <= 490


def test_item_prompt_unknown_slug_falls_back_to_slug_words():
    state = {"inventory": []}
    p = main._build_avatar_prompt(state, "item:ghost-blade", seed=1)
    assert "ghost blade" in p


# ── Endpoints ──

def test_generate_item_image_consumes_one_turn_and_saves_gallery(client):
    _seed("alice")
    _seed_campaign("alice", inventory=[DAGGER])
    tok = _tok()

    r = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "item:worn-ritual-dagger"},
        cookies={"morkrets_token": tok},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["kind"] == "item:worn-ritual-dagger"
    assert body["gallery_count"] == 1
    users = auth.load_users()
    assert users["alice"]["turns_used"] == 1

    # State: galleri-post under item-nyckeln
    state = main.store.get("alice")
    entry = state["avatars"]["item:worn-ritual-dagger"]
    assert entry["ai_generated"] is True
    assert len(entry["gallery"]) == 1
    disk = entry["disk_name"]
    assert disk.startswith("item_worn-ritual-dagger__")
    cid = state["meta"]["campaign_id"]
    img = Path(main.CAMPAIGNS_DIR) / "alice" / cid / "avatars" / disk
    assert img.read_bytes() == b"fake-item-image"

    # GET-bilden (original + tumnagel-bredd)
    g = client.get("/api/campaign/avatar/item:worn-ritual-dagger",
                   cookies={"morkrets_token": tok})
    assert g.status_code == 200
    assert g.content == b"fake-item-image"


def test_generate_item_blocked_for_free_tier(client):
    _seed("freeguy", features={})
    _seed_campaign("freeguy", inventory=[DAGGER])
    tok = _tok("freeguy")

    r = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "item:worn-ritual-dagger"},
        cookies={"morkrets_token": tok},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["feature_locked"] == "image"
    # Ingen turn drog, ingen bild sparades
    users = auth.load_users()
    assert users["freeguy"]["turns_used"] == 0
    state = main.store.get("freeguy")
    assert "item:worn-ritual-dagger" not in (state.get("avatars") or {})


def test_generate_item_rejects_bad_kind(client):
    _seed("alice")
    _seed_campaign("alice", inventory=[DAGGER])
    tok = _tok()
    r = client.post(
        "/api/campaign/avatar/generate",
        json={"provider": "stepfun", "kind": "item:../evil"},
        cookies={"morkrets_token": tok},
    )
    assert r.status_code == 400
