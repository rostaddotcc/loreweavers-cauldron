"""Tester för avatar-purge (2026-08-08).

Purgen raderar filer på disk → dessa tester är säkerhetsnätet. Kritiska
invarianter: den AKTIVA bilden överlever alltid, färska bilder överlever,
och gallery_index pekar rätt efter städningen.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import avatar_purge  # noqa: E402


NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _mk_campaign(tmp_path: Path, avatars: dict, files: dict) -> Path:
    """Bygg en kampanjkatalog: state.json + avatars/-filer."""
    cdir = tmp_path / "campaigns" / "tester" / "abc123def456"
    (cdir / "avatars").mkdir(parents=True)
    state = {
        "meta": {"campaign_id": "abc123def456", "user": "tester"},
        "avatars": avatars,
    }
    (cdir / "state.json").write_text(json.dumps(state))
    for name, content in files.items():
        f = cdir / "avatars" / name
        f.write_bytes(content)
    return cdir / "state.json"


def _gallery(paths, indices):
    return {"gallery": [{"disk_name": n, "ext": ".png", "size": 100, "uploaded": u}
                        for n, u in paths], "gallery_index": indices}


# ═══════════════════════════════════════
# Aktiv bild överlever ALLTID
# ═══════════════════════════════════════

def test_active_image_survives_even_when_ancient(tmp_path):
    """Den aktiva avataren raderas aldrig, hur gammal den än är."""
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery([("a.png", _ts(400))], 0)},
        {"a.png": b"x" * 100},
    )
    stats = avatar_purge.purge_campaign(sp, now=NOW)
    assert (sp.parent / "avatars" / "a.png").exists()
    assert stats["removed_files"] == 0


def test_active_image_survives_purge_of_siblings(tmp_path):
    """Gamla inaktiva bilder bort, aktiv kvar — index följer med."""
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery(
            [("old1.png", _ts(90)), ("old2.png", _ts(80)), ("active.png", _ts(200))], 2)},
        {"old1.png": b"x" * 100, "old2.png": b"x" * 100, "active.png": b"x" * 100},
    )
    stats = avatar_purge.purge_campaign(sp, now=NOW)
    av = sp.parent / "avatars"
    assert not (av / "old1.png").exists()
    assert not (av / "old2.png").exists()
    assert (av / "active.png").exists(), "aktiv bild fick ALDRIG raderas"
    assert stats["removed_entries"] == 2

    state = json.loads(sp.read_text())
    entry = state["avatars"]["player"]
    assert len(entry["gallery"]) == 1
    assert entry["gallery_index"] == 0
    assert entry["disk_name"] == "active.png", "top-level speglar aktiv bild"


# ═══════════════════════════════════════
# Färska bilder överlever
# ═══════════════════════════════════════

def test_recent_inactive_images_survive(tmp_path):
    """Inaktiv men färsk (< 30 dagar) → sparas, spelaren kan bläddra tillbaka."""
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery([("fresh.png", _ts(5)), ("active.png", _ts(1))], 1)},
        {"fresh.png": b"x" * 100, "active.png": b"x" * 100},
    )
    stats = avatar_purge.purge_campaign(sp, now=NOW)
    assert (sp.parent / "avatars" / "fresh.png").exists()
    assert stats["removed_files"] == 0


def test_boundary_29_days_survives_31_days_purged(tmp_path):
    """Gränsen går vid exakt 30 dagar."""
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery(
            [("d29.png", _ts(29)), ("d31.png", _ts(31)), ("active.png", _ts(1))], 2)},
        {"d29.png": b"x" * 100, "d31.png": b"x" * 100, "active.png": b"x" * 100},
    )
    avatar_purge.purge_campaign(sp, now=NOW)
    av = sp.parent / "avatars"
    assert (av / "d29.png").exists(), "29 dagar → behålls"
    assert not (av / "d31.png").exists(), "31 dagar → bort"
    assert (av / "active.png").exists()


# ═══════════════════════════════════════
# Föräldralösa filer
# ═══════════════════════════════════════

def test_orphan_files_removed(tmp_path):
    """Filer som ingen state refererar städas bort."""
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery([("active.png", _ts(1))], 0)},
        {"active.png": b"x" * 100, "orphan.png": b"y" * 500},
    )
    orphan = sp.parent / "avatars" / "orphan.png"
    # Gör föräldralösa filen gammal nog att passera grace-perioden (7 dagar)
    import os
    old = (NOW - timedelta(days=10)).timestamp()
    os.utime(orphan, (old, old))

    stats = avatar_purge.purge_campaign(sp, now=NOW)
    assert not orphan.exists()
    assert (sp.parent / "avatars" / "active.png").exists()
    assert stats["orphans"] == 1


def test_fresh_orphan_survives_grace_period(tmp_path):
    """En bild som just skrivits (pågående generering) rörs inte."""
    import os
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery([("active.png", _ts(1))], 0)},
        {"active.png": b"x" * 100, "just_written.png": b"y" * 100},
    )
    # Sätt mtime till "precis nu" relativt testets syntetiska NOW — annars
    # ligger filens riktiga mtime timmar före NOW och passerar grace-perioden.
    fresh = (NOW - timedelta(minutes=2)).timestamp()
    os.utime(sp.parent / "avatars" / "just_written.png", (fresh, fresh))

    stats = avatar_purge.purge_campaign(sp, now=NOW)
    assert (sp.parent / "avatars" / "just_written.png").exists()
    assert stats["orphans"] == 0


# ═══════════════════════════════════════
# Legacy-format (ingen gallery-nyckel)
# ═══════════════════════════════════════

def test_legacy_single_image_entry_is_protected(tmp_path):
    """Gammal post utan 'gallery' = 1 aktiv bild → raderas aldrig."""
    sp = _mk_campaign(
        tmp_path,
        {"player": {"disk_name": "player.png", "ext": ".png",
                    "size": 100, "uploaded": _ts(300)}},
        {"player.png": b"x" * 100},
    )
    stats = avatar_purge.purge_campaign(sp, now=NOW)
    assert (sp.parent / "avatars" / "player.png").exists()
    assert stats["removed_files"] == 0


# ═══════════════════════════════════════
# dry_run
# ═══════════════════════════════════════

def test_dry_run_deletes_nothing(tmp_path):
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery([("old.png", _ts(99)), ("active.png", _ts(1))], 1)},
        {"old.png": b"x" * 100, "active.png": b"x" * 100},
    )
    before = json.loads(sp.read_text())
    stats = avatar_purge.purge_campaign(sp, dry_run=True, now=NOW)
    assert (sp.parent / "avatars" / "old.png").exists(), "dry_run får inte radera"
    assert stats["removed_files"] == 1, "men den ska rapportera vad den SKULLE ta"
    assert json.loads(sp.read_text()) == before, "state.json orörd vid dry_run"


# ═══════════════════════════════════════
# NPC/DM-nycklar + tom post
# ═══════════════════════════════════════

def test_npc_and_dm_galleries_are_purged_independently(tmp_path):
    sp = _mk_campaign(
        tmp_path,
        {
            "dm": _gallery([("dm_old.png", _ts(60)), ("dm_act.png", _ts(1))], 1),
            "npc:Keeper of Paths": _gallery([("npc_act.png", _ts(500))], 0),
        },
        {"dm_old.png": b"x" * 100, "dm_act.png": b"x" * 100, "npc_act.png": b"x" * 100},
    )
    avatar_purge.purge_campaign(sp, now=NOW)
    av = sp.parent / "avatars"
    assert not (av / "dm_old.png").exists()
    assert (av / "dm_act.png").exists()
    assert (av / "npc_act.png").exists(), "NPC:ns enda bild är aktiv → skyddad"

    state = json.loads(sp.read_text())
    assert "npc:Keeper of Paths" in state["avatars"]


# ═══════════════════════════════════════
# Kontots profilporträtt
# ═══════════════════════════════════════

def test_user_avatar_gallery_purge(tmp_path):
    d = tmp_path / "user_avatars"
    d.mkdir()
    (d / "alice.json").write_text(json.dumps({
        "gallery": [
            {"disk_name": "alice__old.png", "ext": ".png", "size": 100, "uploaded": _ts(120)},
            {"disk_name": "alice__act.png", "ext": ".png", "size": 100, "uploaded": _ts(2)},
        ],
        "gallery_index": 1,
    }))
    (d / "alice__old.png").write_bytes(b"x" * 100)
    (d / "alice__act.png").write_bytes(b"x" * 100)

    stats = avatar_purge.purge_user_avatars(d, now=NOW)
    assert not (d / "alice__old.png").exists()
    assert (d / "alice__act.png").exists()
    assert stats["removed_entries"] == 1

    data = json.loads((d / "alice.json").read_text())
    assert data["gallery_index"] == 0
    assert len(data["gallery"]) == 1


def test_legacy_user_png_never_orphaned(tmp_path):
    """<user>.png används som fallback → får aldrig städas som föräldralös."""
    import os
    d = tmp_path / "user_avatars"
    d.mkdir()
    (d / "bob.json").write_text(json.dumps({
        "gallery": [{"disk_name": "bob__a.png", "ext": ".png", "size": 100, "uploaded": _ts(1)}],
        "gallery_index": 0,
    }))
    (d / "bob__a.png").write_bytes(b"x" * 100)
    legacy = d / "bob.png"
    legacy.write_bytes(b"x" * 100)
    old = (NOW - timedelta(days=200)).timestamp()
    os.utime(legacy, (old, old))

    avatar_purge.purge_user_avatars(d, now=NOW)
    assert legacy.exists(), "legacy-porträttet är fortfarande en giltig fallback"


# ═══════════════════════════════════════
# purge_all över flera kampanjer
# ═══════════════════════════════════════

def test_purge_all_walks_every_campaign(tmp_path):
    campaigns = tmp_path / "campaigns"
    for user, cid in (("u1", "aaaaaaaaaaaa"), ("u2", "bbbbbbbbbbbb")):
        cdir = campaigns / user / cid
        (cdir / "avatars").mkdir(parents=True)
        (cdir / "state.json").write_text(json.dumps({
            "meta": {"campaign_id": cid, "user": user},
            "avatars": {"player": _gallery(
                [("old.png", _ts(90)), ("act.png", _ts(1))], 1)},
        }))
        (cdir / "avatars" / "old.png").write_bytes(b"x" * 1000)
        (cdir / "avatars" / "act.png").write_bytes(b"x" * 1000)

    stats = avatar_purge.purge_all(campaigns, None, now=NOW)
    assert stats["campaigns"] == 2
    assert stats["removed_files"] == 2
    assert stats["freed_bytes"] == 2000
    for user, cid in (("u1", "aaaaaaaaaaaa"), ("u2", "bbbbbbbbbbbb")):
        av = campaigns / user / cid / "avatars"
        assert not (av / "old.png").exists()
        assert (av / "act.png").exists()


def test_purge_all_survives_corrupt_state(tmp_path):
    """En trasig state.json får inte stoppa städningen av övriga."""
    campaigns = tmp_path / "campaigns"
    bad = campaigns / "broken" / "cccccccccccc"
    (bad / "avatars").mkdir(parents=True)
    (bad / "state.json").write_text("{not json")

    good = campaigns / "ok" / "dddddddddddd"
    (good / "avatars").mkdir(parents=True)
    (good / "state.json").write_text(json.dumps({
        "meta": {"campaign_id": "dddddddddddd", "user": "ok"},
        "avatars": {"player": _gallery([("old.png", _ts(90)), ("act.png", _ts(1))], 1)},
    }))
    (good / "avatars" / "old.png").write_bytes(b"x" * 100)
    (good / "avatars" / "act.png").write_bytes(b"x" * 100)

    stats = avatar_purge.purge_all(campaigns, None, now=NOW)
    assert stats["removed_files"] == 1
    assert (good / "avatars" / "act.png").exists()


def test_purge_protects_the_image_the_player_rotated_back_to(tmp_path):
    """Spelaren har bläddrat tillbaka till sitt ÄLDSTA porträtt.

    Den bilden är nu den aktiva och måste överleva — även om den är 300 dagar
    gammal och de nyare bilderna städas bort. Det är hela poängen med pilarna:
    'man kanske vill ha tillbaka sin gamla bild'.
    """
    sp = _mk_campaign(
        tmp_path,
        {"player": _gallery(
            [("old.png", _ts(300)), ("mid.png", _ts(200)), ("new.png", _ts(100))], 0)},
        {"old.png": b"x" * 100, "mid.png": b"x" * 100, "new.png": b"x" * 100},
    )
    avatar_purge.purge_campaign(sp, now=NOW)
    av = sp.parent / "avatars"
    assert av.joinpath("old.png").exists(), "spelarens valda bild fick ALDRIG raderas"
    assert not av.joinpath("mid.png").exists()
    assert not av.joinpath("new.png").exists()

    entry = json.loads(sp.read_text())["avatars"]["player"]
    assert [g["disk_name"] for g in entry["gallery"]] == ["old.png"]
    assert entry["gallery_index"] == 0
    assert entry["disk_name"] == "old.png"

# ═══════════════════════════════════════
# Admin-endpoint + bakgrundsloop
# ═══════════════════════════════════════

def _client_and_main():
    from fastapi.testclient import TestClient
    import main
    return TestClient, main


def test_purge_endpoint_requires_admin(monkeypatch):
    """Icke-admin får 403, oinloggad får 401 — städning är inte spelarfunktion."""
    TestClient, main = _client_and_main()
    from auth import create_token
    monkeypatch.setattr(main.avatar_purge, "purge_all", lambda *a, **k: {
        "campaigns": 0, "removed_files": 0, "removed_entries": 0,
        "freed_bytes": 0, "orphans": 0, "freed_mb": 0.0, "dry_run": False})
    with TestClient(main.app) as c:
        assert c.post("/api/admin/avatars/purge", json={}).status_code == 401
        r = c.post("/api/admin/avatars/purge", json={},
                   cookies={"morkrets_token": create_token("bob", role="user")})
        assert r.status_code == 403


def test_purge_endpoint_passes_days_and_dry_run(monkeypatch):
    """Body-parametrarna når fram till purge_all — och skräp faller tillbaka på 30."""
    TestClient, main = _client_and_main()
    from auth import create_token
    seen = {}

    def fake(campaigns_dir, user_avatars_dir=None, **k):
        seen.clear(); seen.update(k)
        return {"campaigns": 1, "removed_files": 0, "removed_entries": 0,
                "freed_bytes": 0, "orphans": 0, "freed_mb": 0.0,
                "dry_run": k.get("dry_run", False)}

    monkeypatch.setattr(main.avatar_purge, "purge_all", fake)
    admin = {"morkrets_token": create_token("admin", role="admin")}
    with TestClient(main.app) as c:
        r = c.post("/api/admin/avatars/purge", json={"dry_run": True}, cookies=admin)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert seen["dry_run"] is True and seen["older_than_days"] == 30

        c.post("/api/admin/avatars/purge", json={"days": 7}, cookies=admin)
        assert seen["older_than_days"] == 7 and seen["dry_run"] is False

        # Ogiltigt värde får ALDRIG bli 0 dagar (= radera allt inaktivt direkt)
        c.post("/api/admin/avatars/purge", json={"days": "garbage"}, cookies=admin)
        assert seen["older_than_days"] == 30


def test_purge_loop_starts_and_stops_with_app(monkeypatch):
    """Lifespan startar den dagliga loopen och avbryter den vid nedstängning."""
    TestClient, main = _client_and_main()
    monkeypatch.setattr(main.avatar_purge, "purge_all", lambda *a, **k: {
        "campaigns": 0, "removed_files": 0, "removed_entries": 0,
        "freed_bytes": 0, "orphans": 0, "freed_mb": 0.0, "dry_run": False})
    with TestClient(main.app):
        tasks = [t for t in main._BACKGROUND_TASKS
                 if t.get_coro().__qualname__ == "_avatar_purge_loop"]
        assert len(tasks) == 1
        assert not tasks[0].done()
    assert tasks[0].cancelled() or tasks[0].done()
