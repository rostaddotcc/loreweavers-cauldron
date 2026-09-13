"""Server-side avatar thumbnails (?w=64|128|256|512), 2026-09-13.

Täcker BÅDA GET-routerna (/api/campaign/avatar/{kind} + /api/me/avatar) som
delar _avatar_file_response:
  - utan w → original, Cache-Control no-cache (backkompat ljusbox/galleri)
  - med w → diskcachad PNG under thumbs/, Cache-Control public max-age=604800
  - cache-nyckel = src mtime+size → bytt original ger ny tumnagel (gammal rensas)
  - andra anropet träffar cache (thumb-filens mtime oförändrad)
  - w utanför whitelist → 400 (samma stil som _safe_avatar_key)
  - saknad avatar/kind → 404, utan cookie → 401 (auth-beteende orört)
  - webp (fitz bygger utan webp-här) → faller graceful tillbaka till original

Bootstrap som test_free_tier: users.json + CAMPAIGNS_DIR mot tmp, inga
riktiga LLM-anrop, inga /api-register (process-global _REGISTER_TIMES → 429).
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def campaigns_dir(tmp_path, monkeypatch):
    """Kampanjdata OCH user_avatars (CAMPAIGNS_DIR.parent/user_avatars) till tmp."""
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


# ── Hjälpare ─────────────────────────────────────────────────────────────

def _make_png_bytes(width: int = 200, height: int = 200) -> bytes:
    """Riktig PNG byggd med fitz (redan dep — ingen PIL behövs i testen)."""
    import fitz
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), 1)
    pm.clear_with(0)
    return pm.tobytes("png")


WEBP_1x1 = (
    "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA="
)  # minimal giltig 1x1 webp


def _seed_user(username="alice"):
    users = main.load_users()
    users[username] = {"password_hash": hash_password("secret123"), "role": "user"}
    main.save_users(users)
    return create_token(username, "user")


def _seed_campaign_avatar(username, disk_name="player__aaaabbbb.png", content=None):
    """Skapa kampanj + aktiv avatar-post + bildfil på disk. Returnerar (cid, path)."""
    state = main.store.create(username, name="Thumbtest", language="en")
    cid = state["meta"]["campaign_id"]
    av_dir = main.CAMPAIGNS_DIR / username / cid / "avatars"
    av_dir.mkdir(parents=True, exist_ok=True)
    path = av_dir / disk_name
    path.write_bytes(content if content is not None else _make_png_bytes())
    ext = Path(disk_name).suffix.lower()
    state["avatars"] = {
        "player": {"disk_name": disk_name, "ext": ext, "size": path.stat().st_size},
    }
    main.store.save(state)
    return cid, path


def _seed_me_avatar(username, disk_name="alice__ccccdddd.png", content=None):
    """Kontoprofilavatar: user_avatars/<user>.json-galleri + bildfil."""
    av_dir = main._user_avatar_path(username).parent
    av_dir.mkdir(parents=True, exist_ok=True)
    path = av_dir / disk_name
    path.write_bytes(content if content is not None else _make_png_bytes())
    ext = Path(disk_name).suffix.lower()
    main._save_user_avatar_gallery(username, {
        "gallery": [{"disk_name": disk_name, "ext": ext,
                     "size": path.stat().st_size}],
        "gallery_index": 0,
    })
    return path


# ── Kampanj-avatar ───────────────────────────────────────────────────────

def test_no_w_returns_original_backcompat(client):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _, path = _seed_campaign_avatar("alice")
    original = path.read_bytes()

    r = client.get("/api/campaign/avatar/player")
    assert r.status_code == 200
    assert r.content == original
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["content-type"] == "image/png"


def test_w64_returns_smaller_thumb_and_caches_on_disk(client):
    import fitz
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _, path = _seed_campaign_avatar("alice", content=_make_png_bytes(1024, 1024))
    original = path.read_bytes()

    r = client.get("/api/campaign/avatar/player?w=64")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "public, max-age=604800"
    assert len(r.content) < len(original)  # faktiskt mindre än originalet
    thumb = fitz.Pixmap(r.content)          # giltig PNG-bild
    assert (thumb.width, thumb.height) == (64, 64)

    dst = main._avatar_thumb_path(path, 64)
    assert dst.exists(), "cache-fil ska ligga under avatars/thumbs/"
    assert dst.read_bytes() == r.content


def test_second_request_hits_cache(client):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _, path = _seed_campaign_avatar("alice", content=_make_png_bytes(512, 512))

    r1 = client.get("/api/campaign/avatar/player?w=128")
    assert r1.status_code == 200
    dst = main._avatar_thumb_path(path, 128)
    mtime_ns = dst.stat().st_mtime_ns

    r2 = client.get("/api/campaign/avatar/player?w=128")
    assert r2.status_code == 200
    assert r2.content == r1.content
    assert dst.stat().st_mtime_ns == mtime_ns, "andra anropet får inte generera om"


def test_changed_source_regenerates_and_drops_stale(client):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _, path = _seed_campaign_avatar("alice", content=_make_png_bytes(512, 512))

    r1 = client.get("/api/campaign/avatar/player?w=64")
    assert r1.status_code == 200
    old_key = main._avatar_thumb_path(path, 64)
    assert old_key.exists()

    # Ny bild (annan storlek → annan mtime+size-nyckel)
    path.write_bytes(_make_png_bytes(300, 300))
    state = main.store.get("alice")
    assert state is not None
    state["avatars"]["player"]["size"] = path.stat().st_size
    main.store.save(state)

    r2 = client.get("/api/campaign/avatar/player?w=64")
    assert r2.status_code == 200
    new_key = main._avatar_thumb_path(path, 64)
    assert new_key != old_key, "ny fil-nyckel efter ändrat original"
    assert new_key.exists()
    assert not old_key.exists(), "stale thumb rensas bort"


def test_bad_width_rejected_400(client):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _seed_campaign_avatar("alice")
    r = client.get("/api/campaign/avatar/player?w=100")
    assert r.status_code == 400  # whitelist-stil som _safe_avatar_key
    r2 = client.get("/api/campaign/avatar/player?w=0")
    assert r2.status_code == 400


@pytest.mark.parametrize("w", [64, 128, 256, 512])
def test_all_whitelisted_widths_ok(client, w):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _seed_campaign_avatar("alice", content=_make_png_bytes(1024, 1024))
    r = client.get(f"/api/campaign/avatar/player?w={w}")
    assert r.status_code == 200
    assert len(r.content) < 30_000  # tumnaglar från enfärgat png: mycket smått


def test_thumb_never_upscales(client):
    import fitz
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _seed_campaign_avatar("alice", content=_make_png_bytes(32, 32))
    r = client.get("/api/campaign/avatar/player?w=512")
    assert r.status_code == 200
    assert fitz.Pixmap(r.content).width == 32  # skalas ALDRIG upp


def test_missing_avatar_and_kind_404(client):
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    main.store.create("alice", name="Utan avatarer")
    r = client.get("/api/campaign/avatar/player")
    assert r.status_code == 404
    r2 = client.get("/api/campaign/avatar/player?w=64")
    assert r2.status_code == 404
    # Okind/ogiltig kind → 400 (befintligt beteande i _safe_avatar_key, orört)
    r3 = client.get("/api/campaign/avatar/bogus-kind?w=64")
    assert r3.status_code == 400
    # Känd kind men ingen post → 404 även med w
    r4 = client.get("/api/campaign/avatar/dm?w=64")
    assert r4.status_code == 404


def test_unauthenticated_still_401(client):
    r = client.get("/api/campaign/avatar/player?w=64")
    assert r.status_code == 401  # cookie-beteende identiskt med tidigare


def test_uncodable_source_falls_back_to_original(client):
    """webp kan inte avkodas av denna fitz-build → 200 med ORIGINAL och
    no-cache i stället för 500; ingen cache-fil skrivs."""
    import base64
    token = _seed_user()
    client.cookies.set("morkrets_token", token)
    _, path = _seed_campaign_avatar("alice", disk_name="player__webb.webp",
                                    content=base64.b64decode(WEBP_1x1))
    r = client.get("/api/campaign/avatar/player?w=64")
    assert r.status_code == 200
    assert r.content == path.read_bytes()
    assert r.headers["cache-control"] == "no-cache"
    assert not (path.parent / "thumbs").exists() or \
        not list((path.parent / "thumbs").glob("*.png"))


# ── Konto-avatar (/api/me/avatar) — samma delade helper ──────────────────

def test_me_avatar_thumb_roundtrip(client):
    import fitz
    token = _seed_user("bob")
    client.cookies.set("morkrets_token", token)
    path = _seed_me_avatar("bob", content=_make_png_bytes(1024, 1024))

    orig = client.get("/api/me/avatar")
    assert orig.status_code == 200
    assert orig.content == path.read_bytes()
    assert orig.headers["cache-control"] == "no-cache"

    thumb = client.get("/api/me/avatar?w=64")
    assert thumb.status_code == 200
    assert len(thumb.content) < len(orig.content)
    assert fitz.Pixmap(thumb.content).width == 64
    assert thumb.headers["cache-control"] == "public, max-age=604800"
    dst = main._avatar_thumb_path(path, 64)
    assert dst.exists()  # user_avatars/thumbs/<name>__w64__<mtime>_<size>.png

    # ond ut → ogiltig bredd 400 (samma hjälpares ruta)
    assert client.get("/api/me/avatar?w=999").status_code == 400
