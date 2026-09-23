#!/usr/bin/env python3
"""Book of Souls — data generator.

Scans campaign state files, extracts adventurers + NPCs that have generated
avatar images, copies the images next to this script, and writes gallery.json.
Run every 24h via cron to keep the Book of Souls fresh.
"""
import json, os, re, shutil, sys
from datetime import datetime, timedelta

ROOT = os.environ.get("DND_GALLERY_ROOT", "/home/rostads/dnd-llm")
# Sökvägar kan överstyras med env (containern kör samma skript vid
# kampanjradering med DND_GALLERY_DATA_DIR=/app/backend/data/campaigns).
DATA_DIR = os.environ.get("DND_GALLERY_DATA_DIR") or os.path.join(ROOT, "backend/data/campaigns")
OUT_DIR = os.environ.get("DND_GALLERY_OUT_DIR") or os.path.dirname(os.path.abspath(__file__))
AV_DIR = os.path.join(OUT_DIR, "avatars")
MAX_ADVENTURERS = 8
MAX_NPCS = 8
MAX_EQUIP = 8
MAX_NPC_NOTES = 6

# Never show these users' characters (admin test characters are noisy).
EXCLUDE_USERS = set()
# Character names never shown — EMPTY per request 2026-08-06: show ALL painted souls.
NAME_EXCLUDES = set()
# NPC names never shown (player's own NPC-alias etc.)
EXCLUDE_NPCS = set()

os.makedirs(AV_DIR, exist_ok=True)

# Reroll-variant-suffix: backend döper ombilder till npc_<Namn>__<8 hex>.
# Dessa är GAMLA reroll-kopior av samma NPC — bara den stat-registrerade
# (aktuellt valda) avataren ska bli ett kort i boken.
_REROLL_SUFFIX = re.compile(r"__[0-9a-f]{8}$")


def base_npc_name(nm: str) -> str:
    """'Kaelithra the Unbroken__cd525828' → 'Kaelithra the Unbroken'."""
    return _REROLL_SUFFIX.sub("", nm or "").strip()


def first_bullets(notes, max_n=3):
    """Extract the LAST meaningful 'what you know' note(s) from the notes field."""
    if not notes:
        return ""
    bullets = [b.strip() for b in str(notes).split("•") if b.strip()]
    # drop trailing bullets that are just empty or very short
    bullets = [b for b in bullets if len(b) > 12]
    raw = bullets[-1] if bullets else str(notes)
    return cut_at_word(raw, 280)


def first_desc(notes):
    """First character description bullet (the intro/appearance note)."""
    if not notes:
        return ""
    bullets = [b.strip() for b in str(notes).split("•") if b.strip()]
    bullets = [b for b in bullets if len(b) > 12]
    return cut_at_word(bullets[0] if bullets else str(notes), 300)


def last_logbook_mention(logbook, name):
    """Find the most recent logbook entry mentioning this NPC — where they were met/last seen."""
    if not logbook:
        return ""
    name_l = name.lower()
    for entry in reversed(logbook):
        text = (entry.get("text") or "")
        if name_l in text.lower():
            day = entry.get("day")
            return cut_at_word(text, 300) + (f" — Day {day}" if day else "")
    return ""


def first_logbook_day(logbook, name):
    """Campaign day when this NPC was FIRST mentioned in the logbook."""
    name_l = name.lower()
    for entry in logbook:
        if name_l in (entry.get("text") or "").lower():
            return entry.get("day") or 1
    return None


def campaign_date(created_iso, campaign_day):
    """Best-effort calendar date: campaign started on created_iso (Day 1); assume 1 day per campaign day."""
    try:
        start = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        d = start + timedelta(days=max(0, int(campaign_day or 1) - 1))
        return d.strftime("%d %b %Y")
    except Exception:
        return ""


def format_date(created_iso):
    try:
        d = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        return d.strftime("%d %b %Y")
    except Exception:
        return ""


def cut_at_word(text, limit):
    """Truncate at a word boundary, never mid-word, with a trailing ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # back off to the last space so we don't split a word
    idx = cut.rfind(" ")
    if idx > limit * 0.6:
        cut = cut[:idx]
    return cut.rstrip(" ,-—:;") + "…"


def copy_avatar(src, name):
    """Copy the avatar next to the gallery — downscaled WebP when Pillow is
    available (2026-09-23: the raw PNGs run up to 8 MB each, 131 MB gallery;
    WebP ≤1200px q85 shrinks it ~95%). Falls back to a plain copy without PIL."""
    dst_png = os.path.join(AV_DIR, name)
    try:
        from PIL import Image  # container: Pillow via requirements.txt
        im = Image.open(src)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if max(im.size) > 1200:
            _LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
            im.thumbnail((1200, 1200), _LANCZOS)
        dst = os.path.join(AV_DIR, os.path.splitext(name)[0] + ".webp")
        im.save(dst, "WEBP", quality=85, method=6)
        return "avatars/" + os.path.basename(dst)
    except ImportError:
        pass
    except Exception:
        pass
    try:
        shutil.copy2(src, dst_png)
        return "avatars/" + name
    except Exception:
        return None


def main():
    gallery = {"adventurers": [], "npcs": [], "generated_at": None}
    seen_players, seen_npcs = {}, {}

    if not os.path.isdir(DATA_DIR):
        print("ERR: no campaign data dir", DATA_DIR)
        sys.exit(1)

    for user in sorted(os.listdir(DATA_DIR)):
        if user in EXCLUDE_USERS:
            continue
        user_dir = os.path.join(DATA_DIR, user)
        if not os.path.isdir(user_dir):
            continue
        for cid in sorted(os.listdir(user_dir)):
            cdir = os.path.join(user_dir, cid)
            state_path = os.path.join(cdir, "state.json")
            avatars_dir = os.path.join(cdir, "avatars")
            if not os.path.isfile(state_path) or not os.path.isdir(avatars_dir):
                continue
            try:
                s = json.load(open(state_path, encoding="utf-8"))
            except Exception:
                continue

            c = s.get("character") or {}
            name = (c.get("name") or "").strip()
            if name in NAME_EXCLUDES:
                continue
            # ---- adventurer: only if a player avatar image exists ----
            av = (s.get("avatars") or {}).get("player") or {}
            disk = av.get("disk_name")
            img_src = os.path.join(avatars_dir, disk) if disk else None
            if name and img_src and os.path.isfile(img_src) and name not in seen_players:
                rel = copy_avatar(img_src, f"{user}_{cid}_player.png")
                if not rel:
                    continue
                abilities = {k: (v or {}).get("score") for k, v in (c.get("abilities") or {}).items()}
                inv = s.get("inventory") or []
                equipped = [i for i in inv if i.get("equipped")]
                unequipped = [i for i in inv if not i.get("equipped")]
                equip_items = (equipped + unequipped)[:MAX_EQUIP]
                hp = c.get("hp") or {}
                xp = c.get("xp") or {}
                world = s.get("world") or {}
                loc = (world.get("current_location") or "").strip() or "Wandering the realm"
                time_note = (world.get("time") or "").strip()
                meta = s.get("meta") or {}
                spells = (c.get("spells") or [])[:6]
                logbook = world.get("logbook") or []
                journal = ""
                if logbook:
                    last = logbook[-1] if isinstance(logbook, list) else None
                    if last and (last.get("text") or ""):
                        journal = cut_at_word(last["text"], 320) + (f" — Day {last.get('day')}" if last.get("day") else "")
                lore = s.get("lore") or []
                last_lore = ""
                if isinstance(lore, list) and lore:
                    last_lore = cut_at_word(str(lore[-1]), 300)
                gallery["adventurers"].append({
                    "name": name,
                    "img": rel,
                    "race": c.get("race") or "",
                    "class": c.get("class") or "",
                    "level": c.get("level"),
                    "alignment": c.get("alignment") or "",
                    "xp_current": xp.get("current", 0),
                    "xp_next": xp.get("next_level", 300),
                    "hp": hp.get("current"),
                    "hp_max": hp.get("max"),
                    "ac": c.get("ac"),
                    "speed": c.get("speed"),
                    "abilities": abilities,
                    "location": loc,
                    "time": time_note,
                    "spells": [
                        {"name": sp.get("name",""), "level": sp.get("level", 0),
                         "school": sp.get("school",""), "description": (sp.get("description") or "")[:120]}
                        for sp in spells
                    ],
                    "journal": journal,
                    "lore": last_lore,
                    "equipment": [
                        {"name": it.get("name",""), "type": it.get("type","Other"),
                         "equipped": bool(it.get("equipped")),
                         "description": (it.get("description") or "")[:140]}
                        for it in equip_items
                    ],
                    "forged_by": user,
                    "campaign": meta.get("campaign_name") or "",
                    "embarked": format_date(meta.get("created") or ""),
                    "turns_played": meta.get("turn_count", 0),
                })
                seen_players[name] = True

            # ---- NPCs: every painted face gets a page ----
            npcs = s.get("npcs") or []
            world = s.get("world") or {}
            meta = s.get("meta") or {}

            def add_npc(nm, role="", relation="", color=None, notes=""):
                base = base_npc_name(nm)
                if not base or base in EXCLUDE_NPCS or base in seen_npcs:
                    return
                npc_disk = (s.get("avatars") or {}).get(f"npc:{nm}") or {}
                npc_img = npc_disk.get("disk_name")
                # fallback: any npc_<basnamn>* file on disk (inkl. reroll-hash-variants)
                if not npc_img:
                    for cand in sorted(os.listdir(avatars_dir)):
                        if cand.startswith(f"npc_{base}") and cand.endswith(".png"):
                            npc_img = cand
                            break
                npc_src = os.path.join(avatars_dir, npc_img) if npc_img else None
                if not npc_src or not os.path.isfile(npc_src):
                    return
                rel = copy_avatar(npc_src, f"{user}_{cid}_npc_{re.sub(r'[^a-zA-Z0-9]+','_',base)}.png")
                if not rel:
                    return
                note = first_bullets(notes, MAX_NPC_NOTES)
                desc = first_desc(notes)
                met_at = last_logbook_mention(world.get("logbook") or [], base)
                first_day = first_logbook_day(world.get("logbook") or [], base)
                first_met_date = campaign_date(meta.get("created") or "", first_day) if first_day else ""
                gallery["npcs"].append({
                    "name": base,
                    "img": rel,
                    "role": role or "",
                    "color": color or "#c9a227",
                    "relation": relation or "",
                    "note": note,
                    "desc": desc,
                    "met_at": met_at,
                    "first_met_date": first_met_date,
                    "met_by": user,
                })
                seen_npcs[base] = True

            # 1) NPCs registered in state
            for n in npcs:
                nm = (n.get("name") or "").strip()
                add_npc(nm, role=n.get("role") or "", relation=n.get("relation") or "",
                        color=n.get("color"), notes=n.get("notes") or "")

            # 2) painted faces on disk that state never registered (user may have
            #    generated a portrait directly) — their name comes from the file.
            #    Reroll-hash-variants (npc_X__<hash>) av en redan sedd NPC hoppas —
            #    bara det stat-valda kortet ska synas.
            for fname in sorted(os.listdir(avatars_dir)):
                if not fname.startswith("npc_") or not fname.endswith(".png"):
                    continue
                base = base_npc_name(fname[4:-4].strip())
                if base and base not in seen_npcs and base not in EXCLUDE_NPCS:
                    add_npc(base)

    gallery["generated_at"] = __import__("datetime").datetime.now().isoformat(timespec="minutes")
    # Most-played first: level desc, then XP asc (closer to next level = more played)
    gallery["adventurers"].sort(key=lambda a: (-(a.get("level") or 0), -((a.get("xp_current") or 0) * 1.0 / max(1, (a.get("xp_next") or 1)))))
    out = os.path.join(OUT_DIR, "gallery.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(gallery, f, ensure_ascii=False, indent=1)
    # Rensa föräldralösa avatarkopior: gamla rerolls, raderade kampanjers
    # showcase/galleribilder — allt som inte refereras av det färska galleriet.
    referenced = {os.path.basename(e["img"]) for e in gallery["adventurers"] + gallery["npcs"]}
    purged = 0
    for fname in sorted(os.listdir(AV_DIR)):
        if fname not in referenced:
            try:
                os.remove(os.path.join(AV_DIR, fname))
                purged += 1
            except OSError:
                pass
    if purged:
        print(f"purged {purged} orphan avatar(s) from {AV_DIR}")
    print(f"OK: {len(gallery['adventurers'])} adventurers, {len(gallery['npcs'])} npcs -> {out}")


if __name__ == "__main__":
    main()
