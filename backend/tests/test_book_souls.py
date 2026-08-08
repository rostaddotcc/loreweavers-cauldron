"""Book of Souls — gen_gallery.py (2026-08-08).

Täcker:
  - reroll-variants (npc_<Namn>__<8 hex>.png) dedupliceras till EN kort per NPC
    (det stat-registrerade, aktuellt valda kortet)
  - föräldralösa avatarkopior (gamla rerolls + raderade kampanjers
    showcase/galleribilder) rensas från book-souls/avatars
  - försvinner en kampanjkatalog → försvinner kortet + bilderna vid nästa körning

Kör skriptet som subprocess med env-överstyrda sökvägar (samma mekanism som
backend-vägen _refresh_book_of_souls använder i containern).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR.parent / "frontend" / "book-souls" / "gen_gallery.py"


def _png(path: Path, size: int = 64, tag: bytes = b"DATA") -> None:
    # dummy-bytes med tag — gen_gallery kopierar bara (validerar inte innehåll)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + tag + bytes([0] * size))


def _make_campaign(data_dir: Path, user: str, cid: str, npc_name: str, npc_disk: str) -> None:
    cdir = data_dir / user / cid
    cdir.mkdir(parents=True, exist_ok=True)
    state = {
        "meta": {"user": user, "campaign_id": cid, "campaign_name": "Burete",
                 "created": "2026-08-01T12:00:00+00:00"},
        "character": {"name": "Xylith", "race": "Tiefling", "class": "Warlock", "level": 3,
                      "hp": {"current": 22, "max": 22}, "ac": 13,
                      "abilities": {"STR": {"score": 10}, "DEX": {"score": 14}, "CON": {"score": 12},
                                    "INT": {"score": 10}, "WIS": {"score": 10}, "CHA": {"score": 16}}},
        "npcs": [{"name": npc_name, "role": "Barkeep", "relation": "neutral",
                  "notes": "• Skäggig och bred. • Känner till undergången."}],
        "avatars": {f"npc:{npc_name}": {"disk_name": npc_disk}},
        "world": {"logbook": [{"day": 2, "text": f"Träffade {npc_name} i krogen."}],
                  "current_location": "Burete"},
        "inventory": [],
    }
    (cdir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    # npc-avatar + gamla reroll-kopior + en player-kopia som INTE refereras.
    # Unikt innehåll per fil så testet kan bevisa VILKEN avatar som valdes.
    _png(cdir / "avatars" / npc_disk, tag=b"STATE")
    _png(cdir / "avatars" / f"npc_{npc_name}__2bcf662f.png", tag=b"OLD1")
    _png(cdir / "avatars" / f"npc_{npc_name}__443655b8.png", tag=b"OLD2")
    _png(cdir / "avatars" / "player__d769eabd.png", tag=b"PLAYER")


def _run(data_dir: Path, out_dir: Path):
    env = dict(os.environ)
    env["DND_GALLERY_DATA_DIR"] = str(data_dir)
    env["DND_GALLERY_OUT_DIR"] = str(out_dir)
    r = subprocess.run([sys.executable, str(SCRIPT)], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads((out_dir / "gallery.json").read_text(encoding="utf-8"))


def test_reroll_variants_dedupe_to_one_card(tmp_path):
    """elfa-scenariot: 5 reroll-kopior + stat-registrerad → EN Kaelithra-kort."""
    data = tmp_path / "data"
    out = tmp_path / "out"
    _make_campaign(data, "elfa", "57c88bb4ed1a", "Kaelithra the Unbroken",
                   "npc_Kaelithra the Unbroken__cd525828.png")

    g = _run(data, out)

    kael = [n for n in g["npcs"] if n["name"] == "Kaelithra the Unbroken"]
    assert len(kael) == 1, [n["name"] for n in g["npcs"]]
    assert kael[0]["met_by"] == "elfa"
    # det aktuellt valda kortet använder den STAT-refererade avataren
    # (inte någon av de gamla reroll-kopiorna)
    copied = (out / kael[0]["img"]).read_bytes()
    assert b"STATE" in copied
    # inga hash-suffix-namn som kort
    assert not any("__" in n["name"] for n in g["npcs"])


def test_orphan_purge_removes_stale_copies(tmp_path):
    """Bilder som inte refereras av det färska galleriet (gamla rerolls,
    player-kopia utan stat-referens) rensas ur book-souls/avatars."""
    data = tmp_path / "data"
    out = tmp_path / "out"
    _make_campaign(data, "elfa", "57c88bb4ed1a", "Kaelithra the Unbroken",
                   "npc_Kaelithra the Unbroken__cd525828.png")

    _run(data, out)

    files = sorted((out / "avatars").iterdir())
    names = [f.name for f in files]
    assert len(files) == 1, names  # bara den stat-refererade NPC-kopian finns kvar
    assert "Kaelithra_the_Unbroken.png" in names[0]


def test_deleted_campaign_removes_card_and_images(tmp_path):
    """Raderas kampanjkatalogen → kortet + alla dess galleribilder försvinner."""
    data = tmp_path / "data"
    out = tmp_path / "out"
    _make_campaign(data, "elfa", "57c88bb4ed1a", "Kaelithra the Unbroken",
                   "npc_Kaelithra the Unbroken__cd525828.png")
    g1 = _run(data, out)
    assert len(g1["npcs"]) == 1

    # kampanjen raderas (som store.delete gör)
    import shutil
    shutil.rmtree(data / "elfa" / "57c88bb4ed1a")

    g2 = _run(data, out)
    assert g2["npcs"] == []
    assert sorted((out / "avatars").iterdir()) == []
