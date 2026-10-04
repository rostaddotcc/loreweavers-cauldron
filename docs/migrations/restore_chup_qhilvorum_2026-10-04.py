#!/usr/bin/env python3
"""Engångs: återställ Qhilvorum i kampanjen "I WIN" (chup / 3919f6c65d30).

BAKGRUND
  2026-10-03 skrev POST /api/vault/characters/{id}/use in valv-karaktären
  "The Lattice" (nivå 1, 0 XP) i den AKTIVA kampanjen och ersatte därmed
  Qhilvorum (nivå 2, 600 XP, 91 turer). Bara `character` + `inventory` byttes —
  npcs, quests, lore, world och combat är orörda i state.json.

KÄLLOR
  - basark:      vaults/chup/413dd4e29e.json (sparad 2026-10-01 10:47, en minut
                 innan kampanjen skapades)
  - tillväxt:    transcripts/session-001.jsonl — Lorekeeper-rapporterna bär
                 XP, level-up, HP-slog, spell slots, spells, items och
                 character updates ordagrant.

KÖRNING
  Torrkör mot en KOPIA först:
    DATA_DIR=/tmp/qrestore python3 restore_chup_qhilvorum.py            (dry-run)
    DATA_DIR=/tmp/qrestore python3 restore_chup_qhilvorum.py --apply
  Live (root-ägda filer → kör i containern):
    docker cp <script> loreweavers-cauldron:/app/backend/scripts/
    docker exec -w /app loreweavers-cauldron python3 /app/backend/scripts/restore_chup_qhilvorum.py --apply

SÄKERHET
  - --apply backar upp state.json + alla transkript till backups/patch-<ts>/
    INNAN något skrivs, skriver atomiskt (tmp + os.replace) och appendar en
    assistant-notis i senaste session (renderas som DM-bubbla hos spelaren).
  - Rör ALDRIG andra nycklar än character, inventory och meta.vault_id.
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

USER = "chup"
CAMPAIGN_ID = "3919f6c65d30"
VAULT_ID = "413dd4e29e"          # Qhilvorums basark i valvet

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/backend/data"))
CAMPAIGN_DIR = DATA_DIR / "campaigns" / USER / CAMPAIGN_ID
STATE_PATH = CAMPAIGN_DIR / "state.json"
VAULT_PATH = DATA_DIR / "vaults" / USER / f"{VAULT_ID}.json"

NOTICE = (
    "⚒ **The ledger is mended.** A mishap at the Vault on 3 October replaced "
    "Qhilvorum's sheet with a stored copy while your adventure was still running. "
    "Your wizard is restored — level 2, 600 XP, the Hymn-Cutter, Scurry of the "
    "Wet Stone and every entry the Lorekeeper wrote down. The story never left; "
    "only the sheet was lost. (Fixed 2026-10-04 — Cooked Souls can no longer "
    "overwrite a hero mid-adventure.)"
)


# ── Tillväxt ur transkriptet ────────────────────────────────────────────
def parse_transcript(path: Path) -> dict:
    """Plocka ut XP/level/HP/slots/spells/items/updates ur Lorekeeper-raderna."""
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = {"xp": None, "level": None, "hp": None, "slots": None, "slots_max": None,
           "spells": [], "item_events": [], "updates": []}
    for r in rows:
        if r.get("role") != "guardian":
            continue
        c = r.get("content") or ""
        tm = re.search(r"Turn (\d+)", c)
        turn = int(tm.group(1)) if tm else None

        for m in re.finditer(r"([+-]\d+)\s*XP[*\s]*\(([\d\s]+)/([\d\s]+)\)", c):
            out["xp"] = (int(m.group(2).replace(" ", "")), int(m.group(3).replace(" ", "")))
        for m in re.finditer(r"LEVEL UP → (\d+)", c):
            out["level"] = int(m.group(1))
        for m in re.finditer(r"(\d+)\s*damage[*\s]*→\s*HP\s*(\d+)/(\d+)", c):
            out["hp"] = (int(m.group(2)), int(m.group(3)))
        for m in re.finditer(r"Healing[*\s]*→\s*HP\s*(\d+)/(\d+)", c):
            out["hp"] = (int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"spell slots (\d+)/(\d+) left", c):
            out["slots"], out["slots_max"] = int(m.group(1)), int(m.group(2))
        for m in re.finditer(r"Spell slots now:[*\s]*(\d+)", c):
            out["slots_max"] = int(m.group(1))
        for m in re.finditer(r"Spell learned:[*\s]*([^(\n]+)\(level (\d+)\)", c):
            out["spells"].append((m.group(1).strip(), int(m.group(2))))
        # Item-händelser i LÄSORDNING (samma rad kan ha både + och −:
        # "📦 New item: Hymn-Cutter 🗑️ Item removed: Toller's Sinew-Dagger")
        events = []
        for m in re.finditer(r"New item:[*\s]*([^\n:*]+)", c):
            events.append((m.start(), "add", m.group(1).strip()))
        for m in re.finditer(r"Item removed:[*\s]*([^\n:*]+)", c):
            events.append((m.start(), "remove", m.group(1).strip()))
        for _, kind, name in sorted(events):
            out["item_events"].append((kind, name))
        for m in re.finditer(r"Character update \((\w+)\):[*\s]*([^\n]+?)[*\s]*$", c, re.M):
            out["updates"].append({"field": m.group(1), "text": m.group(2).strip(),
                                   "turn": turn})
    return out


def build_character(base: dict, growth: dict) -> dict:
    ch = json.loads(json.dumps(base))          # djup kopia av basarket
    if growth["level"]:
        ch["level"] = growth["level"]
    if growth["xp"]:
        ch["xp"] = {"current": growth["xp"][0], "next_level": growth["xp"][1]}
    if growth["hp"]:
        ch["hp"] = {"current": growth["hp"][0], "max": growth["hp"][1], "temp": 0}
    if growth["slots_max"]:
        ch["spell_slots"] = {"current": growth["slots"] if growth["slots"] is not None
                             else growth["slots_max"], "max": growth["slots_max"]}

    known = {s.get("name") for s in ch.get("spells") or []}
    for name, lvl in growth["spells"]:
        if name in known:
            continue
        ch.setdefault("spells", []).append({
            "name": name, "level": lvl, "school": "Transmutation",
            "casting_time": "1 action", "damage_dice": "",
            "description": ("Forged from the hymns of slain foes — a permanent "
                            "1st-level transmutation of wet-stone stubbornness."),
        })
    # Guardian-tillväxten (append-only) — ordagrant ur rapporten
    if growth["updates"]:
        ch["updates"] = growth["updates"]
    return ch


def build_inventory(base_inv: list, growth: dict) -> list:
    inv = json.loads(json.dumps(base_inv))
    for kind, name in growth["item_events"]:
        if kind == "add":
            if not any((i.get("name") or "") == name for i in inv):
                inv.append({"name": name, "qty": 1, "weight": 0,
                            "lore": "Recovered from the Rot-touched Marrow."})
        else:
            inv = [i for i in inv if (i.get("name") or "") != name]
    return inv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="skriv (annars torrkörning)")
    args = ap.parse_args()

    for p in (STATE_PATH, VAULT_PATH):
        if not p.exists():
            print(f"❌ saknar {p}")
            return 1

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    vault_entry = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    sessions = sorted((CAMPAIGN_DIR / "transcripts").glob("session-*.jsonl"))
    if not sessions:
        print("❌ inga transkript")
        return 1

    growth = parse_transcript(sessions[0])
    character = build_character(vault_entry.get("character") or {}, growth)
    inventory = build_inventory(vault_entry.get("inventory") or [], growth)

    print("── TILLVÄXT UR TRANSKRIPTET ──")
    print("  level      :", growth["level"], "| xp:", growth["xp"])
    print("  hp         :", growth["hp"], "| slots:", growth["slots"], "/", growth["slots_max"])
    print("  spells     :", growth["spells"])
    print("  items      :", growth["item_events"])
    print("  updates    :", len(growth["updates"]))
    print("── RESULTAT ──")
    print("  character  :", {k: character.get(k) for k in ("name", "class", "level", "xp", "hp", "spell_slots")})
    print("  spells     :", [s.get("name") for s in character.get("spells") or []])
    print("  inventory  :", [i.get("name") for i in inventory])

    def changed_keys(a, b):
        ka, kb = set(a), set(b)
        return sorted(k for k in kb if json.dumps(a.get(k), sort_keys=True) != json.dumps(b.get(k), sort_keys=True))

    new_state = json.loads(json.dumps(state))
    new_state["character"] = character
    new_state["inventory"] = inventory
    new_state.setdefault("meta", {})["vault_id"] = VAULT_ID

    print("── DIFF (state.json) ──")
    print("  ändrade nycklar :", changed_keys(state, new_state))
    print("  meta.vault_id   :", new_state["meta"].get("vault_id"))

    if not args.apply:
        print("\n(torrkörning — inget skrivet)")
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = CAMPAIGN_DIR / "backups" / f"patch-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATE_PATH, backup_dir / "state.json")
    for s in sessions:
        shutil.copy2(s, backup_dir / s.name)
    print(f"🗄️  backup → {backup_dir}")

    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(new_state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE_PATH)
    print("✅ state.json skriven (atomiskt)")

    last = sessions[-1]
    with last.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"role": "assistant", "content": NOTICE,
                            "ts": datetime.now(timezone.utc).isoformat()},
                           ensure_ascii=False) + "\n")
    print(f"📜 notis appendad → {last.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
