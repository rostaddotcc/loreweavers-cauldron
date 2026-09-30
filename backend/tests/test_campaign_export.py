"""2026-09-30: Campaign-export rebuild — allt relevant, snyggt strukturerat.

Rostads översyn: zippen ska innehålla HELA kampanjen (tidigare saknades
quests, inventory/currency, facts, loggbok, chapters/arcs, attachments;
guardian-rader etiketterades som "Spelare", __VAKNA_DM__ läckte, README
var på svenska i en engelsk UI). Zip-layout (engelsk):

  README.md · campaign.json · character/{sheet.md,sheet.json,inventory.md}
  transcript/session-*.{md,jsonl} · world/{npcs,locations,quests,lore,facts}.md
  journal/{logbook,summaries,chapters,arcs}.md · attachments/ · images/
"""

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import auth  # noqa: E402
import main  # noqa: E402
import state_manager as sm  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from extraction import Fact  # noqa: E402


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
    monkeypatch.setattr(sm, "VAULTS_DIR", tmp_path / "vaults")
    monkeypatch.setattr(main, "VAULTS_DIR", tmp_path / "vaults")
    return d


@pytest.fixture(autouse=True)
def ledger_file(tmp_path, monkeypatch):
    f = tmp_path / "_billing_ledger.json"
    monkeypatch.setattr(main, "_LEDGER_FILE", f)
    return f


@pytest.fixture(autouse=True)
def stripe_env(monkeypatch):
    monkeypatch.setattr(main, "STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr(main, "STRIPE_WEBHOOK_SECRET", "whsec_test123")


@pytest.fixture
def client(users_file, campaigns_dir, ledger_file, stripe_env):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed(username="alice", features=None):
    main.save_users({
        username: {"password_hash": hash_password("secret123"), "role": "player",
                   "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": "2026-08-04", "subscription_status": "tier1",
                   "subscription_until": None,
                   "features": features if features is not None else {"export": True},
                   "start_bonus_granted": True,
                   "email": "alice@example.com"},
    })


def _tok(username="alice", role="player"):
    return create_token(username, role)


def _rich_campaign(client) -> dict:
    """Skapa + berika en kampanj med ALLT exporten ska fånga."""
    _seed()
    main.store.create("alice", name="Emberfall", language="en")
    st = main.store.get("alice")
    assert st is not None

    st["character"].update({
        "name": "Vesper Nighthollow", "race": "elf", "class": "wizard",
        "level": 3, "alignment": "chaotic good", "background": "sage",
        "ac": 13, "initiative": 2, "perception": 12, "speed": "30 ft",
        "proficiency": 2, "hp": {"current": 14, "max": 18, "temp": 2},
        "spell_slots": {"current": 3, "max": 4},
        "xp": {"current": 950, "next_level": 2700},
        "abilities": {k: {"score": 10 + i, "mod": i // 2 - 1} for i, k in enumerate(
            ["STR", "DEX", "CON", "INT", "WIS", "CHA"])},
        "skills": [{"name": "Arcana", "ability": "INT", "proficient": True},
                   {"name": "Stealth", "ability": "DEX", "proficient": False}],
        "features": [{"name": "Spellcasting", "level": 1, "description": "Wizard magic."}],
        "spells": [{"name": "Fire Bolt", "level": 0, "school": "evocation",
                    "casting_time": "1 action", "damage_dice": "1d10",
                    "description": "Hurl a mote of fire."}],
        "traits": ["Keeps a grudge ledger"],
        "resistances": [], "darkvision": "60 ft",
        "gear": "quarterstaff · spellbook",
        "story": "Exiled from the Ember Academy.",
        "notes": "Ask the innkeeper about the cellar.",
        "max_weight_lbs": 135,
    })
    st["inventory"] = [
        {"name": "Emberstaff", "type": "Weapon", "category": "weapon",
         "qty": 1, "weight": 4, "equipped": True, "rarity": "rare",
         "damage": "1d6 bludgeoning", "properties": ["versatile"],
         "lore": "Warm to the touch."},
        {"name": "Healing Potion", "type": "Potion", "category": "potion",
         "qty": 2, "weight": 0.5, "rarity": "normal"},
    ]
    st["currency"] = {"pp": 1, "gp": 42, "sp": 7, "cp": 3}
    st["npcs"] = [
        {"name": "Mira", "role": "innkeeper", "relation": "allierad",
         "notes": "Knows the cellar secret.", "alive": True},
        {"name": "Grob", "role": "bandit", "relation": "fiende",
         "notes": "", "alive": False},
    ]
    st["quests"] = [
        {"name": "Find the ember shard", "description": "In the cellar.",
         "status": "aktiv", "created_turn": 2, "xp_reward": 100},
        {"name": "Escort Mira", "description": "To the ford.",
         "status": "completed", "created_turn": 1, "completed_turn": 5},
        {"name": "Pay the ferryman", "description": "",
         "status": "failed", "created_turn": 3},
    ]
    st["lore"] = ["The Ember Academy burned in the third age.",
                  "Cellars under Emberfall flood at high tide."]
    st["pinned_facts"] = ["Mira owes Vesper a favor."]
    st["world"].update({
        "current_location": "Emberfall", "time": "dusk",
        "visited_locations": ["Emberfall"],
        "travel_log": [{"from": "Ford", "to": "Emberfall", "day": 2}],
        "logbook": [{"day": 1, "turn": 2, "text": "Arrived at Emberfall."},
                    {"day": 1, "turn": 4, "text": "Met Mira at the inn."}],
    })
    st["locations"] = [
        {"name": "Emberfall", "description": "A rain-slick village.",
         "terrain": "village", "x": 50, "y": 50},
        {"name": "The Ford", "description": "Crossing.", "x": 60, "y": 40},
    ]
    main.store.save(st)

    cid = st["meta"]["campaign_id"]
    cdir = main.CAMPAIGNS_DIR / "alice" / cid

    # Transkript: player/DM/guardian/system + sentinel som INTE ska läcka
    tdir = cdir / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"role": "user", "content": "__VAKNA_DM__", "ts": "2026-09-01T10:00:00+00:00"},
        {"role": "user", "content": "I push open the cellar door.", "ts": "2026-09-01T10:01:00+00:00"},
        {"role": "assistant", "content": "The hinges scream in the dark.", "ts": "2026-09-01T10:01:30+00:00"},
        {"role": "guardian", "content": "🦉 Journal: the door was opened.", "ts": "2026-09-01T10:02:00+00:00", "meta": {"turn": 1}},
        {"role": "guardian", "content": "ℹ️ Tier set to Free.", "ts": "2026-09-01T10:03:00+00:00", "meta": {"log": True}},
    ]
    (tdir / "session-001.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")

    # Summaries: alla TRE nivåer (scene/chapter/arc)
    sdir = cdir / "summaries"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "summary-turn-0020.json").write_text(json.dumps(
        {"turn": 20, "text": "They descended into the cellar."}))
    (sdir / "chapter-001.json").write_text(json.dumps(
        {"chapter": 1, "text": "### Chapter: The Cellar", "created": "2026-09-02T00:00:00+00:00"}))
    (sdir / "campaign-arc-001.json").write_text(json.dumps(
        {"arc": 1, "text": "Arc I — Emberfall's secret.", "created": "2026-09-03T00:00:00+00:00"}))

    # Attachments: originalnamn + krock (dedup)
    att = cdir / "attachments"
    att.mkdir(parents=True, exist_ok=True)
    (att / "aaa111.md").write_text("# House rules\nNo PVP.")
    (att / "bbb222.md").write_text("second file")
    st["attachments"] = [
        {"id": "aaa111", "name": "rules.md", "disk_name": "aaa111.md", "ext": ".md",
         "size": 20, "uploaded": "2026-09-01T00:00:00+00:00"},
        {"id": "bbb222", "name": "rules.md", "disk_name": "bbb222.md", "ext": ".md",
         "size": 11, "uploaded": "2026-09-02T00:00:00+00:00"},
    ]
    main.store.save(st)

    # Avatars (+ thumbs som INTE ska hamna i zippen)
    av = cdir / "avatars"
    (av / "thumbs").mkdir(parents=True, exist_ok=True)
    (av / "player.png").write_bytes(b"\x89PNG player")
    (av / "npc_Mira__x1.png").write_bytes(b"\x89PNG mira")
    (av / "thumbs" / "player__small.png").write_bytes(b"\x89PNG thumb")

    return st


def _export(client) -> zipfile.ZipFile:
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_export_full_structure(client):
    _rich_campaign(client)
    zf = _export(client)
    names = zf.namelist()
    for expected in [
        "README.md", "campaign.json",
        "character/sheet.md", "character/sheet.json", "character/inventory.md",
        "transcript/session-001.md", "transcript/session-001.jsonl",
        "world/npcs.md", "world/locations.md", "world/quests.md",
        "world/lore.md", "world/facts.md",
        "journal/logbook.md", "journal/summaries.md",
        "journal/chapters.md", "journal/arcs.md",
        "attachments/rules.md", "attachments/rules (2).md",
        "images/avatars/player.png", "images/avatars/npc_Mira__x1.png",
    ]:
        assert expected in names, f"saknas: {expected}"
    # tumnaglar är derivat — följer INTE med
    assert not any("thumbs" in n for n in names)


def test_export_readme_overview(client):
    _rich_campaign(client)
    zf = _export(client)
    readme = zf.read("README.md").decode()
    assert "# Emberfall" in readme
    assert "Vesper Nighthollow" in readme
    assert "1 active · 3 total" in readme          # quest-räkning
    assert "NPCs met:** 2" in readme
    # engelsk chrome — inga svenska etiketter
    for sv in ("Kampanj-ID", "Senast uppdaterad", "Turer:", "Okänd"):
        assert sv not in readme


def test_export_campaign_json_is_full_state(client):
    _rich_campaign(client)
    zf = _export(client)
    raw = json.loads(zf.read("campaign.json").decode())
    assert raw["meta"]["campaign_name"] == "Emberfall"
    assert raw["character"]["name"] == "Vesper Nighthollow"
    assert len(raw["inventory"]) == 2
    assert raw["currency"]["gp"] == 42
    assert len(raw["quests"]) == 3


def test_export_character_sheet(client):
    _rich_campaign(client)
    zf = _export(client)
    md = zf.read("character/sheet.md").decode()
    assert "# Vesper Nighthollow" in md
    assert "elf · wizard · Level 3 · chaotic good" in md
    assert "**HP:** 14/18 (+2 temp)" in md
    assert "## Abilities" in md and "| STR |" in md
    assert "● Arcana" in md and "○ Stealth" in md          # prof-markering
    assert "### Cantrips" in md and "Fire Bolt" in md
    assert "Exiled from the Ember Academy" in md
    assert "Ask the innkeeper about the cellar" in md      # spelarens Notes
    # rå-JSON kompletterar
    js = json.loads(zf.read("character/sheet.json").decode())
    assert js["level"] == 3


def test_export_inventory(client):
    _rich_campaign(client)
    zf = _export(client)
    md = zf.read("character/inventory.md").decode()
    assert "**42** GP" in md and "**1** PP" in md
    assert "Emberstaff" in md and "✦" in md                # equipped-stjärna
    assert "_(rare)_" in md
    assert "Healing Potion** ×2" in md
    assert "Warm to the touch" in md                        # lore-text
    assert "Carrying 5 / 135 lbs" in md                     # 4 + 2×0.5


def test_export_transcript_labels_and_sentinel(client):
    _rich_campaign(client)
    zf = _export(client)
    md = zf.read("transcript/session-001.md").decode()
    assert "__VAKNA_DM__" not in md                         # sentinel borta
    assert "⚔️ Player" in md and "I push open the cellar door." in md
    assert "🧙 Dungeon Master" in md and "The hinges scream" in md
    assert "🦉 Lorekeeper" in md and "Journal: the door was opened." in md
    assert "📣 System" in md and "Tier set to Free" in md
    # rå-JSONL följer med oförändrad (inkl. sentinel — det är rådatan)
    raw = zf.read("transcript/session-001.jsonl").decode()
    assert "__VAKNA_DM__" in raw


def test_export_world_docs(client):
    _rich_campaign(client)
    zf = _export(client)
    npcs = zf.read("world/npcs.md").decode()
    assert "## Mira" in npcs and "innkeeper · allierad" in npcs
    assert "# Fallen" in npcs and "## Grob" in npcs         # död NPC-sektion

    locs = zf.read("world/locations.md").decode()
    assert "## Emberfall 📍 _You are here_" in locs
    assert "The Ford" in locs
    assert "Day 2: Ford → Emberfall" in locs                # travel_log

    quests = zf.read("world/quests.md").decode()
    assert "## ⚑ Active" in quests and "Find the ember shard" in quests
    assert "## ✅ Completed" in quests and "Escort Mira" in quests
    assert "## 💀 Failed" in quests and "Pay the ferryman" in quests
    assert "100 XP" in quests

    lore = zf.read("world/lore.md").decode()
    assert "The Ember Academy burned" in lore


def test_export_journal_books(client):
    _rich_campaign(client)
    zf = _export(client)
    log = zf.read("journal/logbook.md").decode()
    assert "## Day 1" in log
    assert "Arrived at Emberfall." in log and "Met Mira at the inn." in log

    assert "Turn 20" in zf.read("journal/summaries.md").decode()
    ch = zf.read("journal/chapters.md").decode()
    assert "## Chapter 1" in ch and "The Cellar" in ch
    arc = zf.read("journal/arcs.md").decode()
    assert "## Arc 1" in arc and "Emberfall's secret" in arc


def test_export_facts_register(client, monkeypatch):
    """Facts-registret (Codex Facts-flik) ska med — active + superseded."""
    _rich_campaign(client)

    class _FakeReg:
        def __init__(self, username, campaign_id="", **kw):
            self._facts = [
                Fact(category="location", text="The cellar floods at high tide.",
                     source_turn=2, confidence=0.9),
                Fact(category="npc", text="Mira trusts Vesper.", source_turn=3,
                     superseded_by="newid1"),
            ]

    monkeypatch.setattr(main, "FactRegister", _FakeReg)
    zf = _export(client)
    md = zf.read("world/facts.md").decode()
    assert "The cellar floods at high tide." in md
    assert "## Location" in md
    assert "📌 Mira owes Vesper a favor." in md             # pinned
    assert "~~Mira trusts Vesper.~~" in md                  # superseded


def test_export_attachments_dedup_and_content(client):
    _rich_campaign(client)
    zf = _export(client)
    assert zf.read("attachments/rules.md").decode() == "# House rules\nNo PVP."
    assert zf.read("attachments/rules (2).md").decode() == "second file"


def test_export_avatar_bytes(client):
    _rich_campaign(client)
    zf = _export(client)
    assert zf.read("images/avatars/player.png") == b"\x89PNG player"
    assert zf.read("images/avatars/npc_Mira__x1.png") == b"\x89PNG mira"


def test_export_empty_campaign_still_complete(client):
    """Ny kampanj utan innehåll → alla filer finns, med placeholder-text."""
    _seed()
    main.store.create("alice", name="Fresh", language="en")
    zf = _export(client)
    names = zf.namelist()
    assert "character/sheet.md" in names
    assert "No character created yet." in zf.read("character/sheet.md").decode()
    assert "No quests yet." in zf.read("world/quests.md").decode()
    assert "No one met yet." in zf.read("world/npcs.md").decode()
    assert "_Pockets empty._" in zf.read("character/inventory.md").decode()
    assert "No facts recorded yet." in zf.read("world/facts.md").decode()
    assert "_No places discovered yet._" in zf.read("world/locations.md").decode()


def test_export_filename_and_headers(client):
    st = _rich_campaign(client)
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    cid = st["meta"]["campaign_id"]
    assert f'filename="the-lore-weavers-cauldron-{cid}.zip"' in r.headers["content-disposition"]


def test_export_gate_free_403(client):
    """Export är fortfarande en betald förmån."""
    _seed(features={})
    main.save_users({
        "alice": {"password_hash": hash_password("secret123"), "role": "player",
                  "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                  "reset_date": "2026-08-04", "subscription_status": "free",
                  "subscription_until": None, "features": {},
                  "start_bonus_granted": True, "email": "alice@example.com"},
    })
    main.store.create("alice", name="T", language="en")
    r = client.get("/api/campaign/export", cookies={"morkrets_token": _tok()})
    assert r.status_code == 403
