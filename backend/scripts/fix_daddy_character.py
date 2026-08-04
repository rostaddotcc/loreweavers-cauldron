#!/usr/bin/env python3
"""Emergency character-sheet restoration for daddy's campaign 'Oh boy' (425d34f9e222).

Root cause: kampanjen startades utan karaktärsskapande (direkt __VAKNA_DM__),
så state['character'] fick aldrig ett grundark — Guardian byggde tillväxtdata
(updates/xp/spells/hp) ovanpå tomhet, och Codex/DM visade ett tomt ark.

Patchen:
  1. Backar upp state.json + transcripts
  2. Rekonstruerar ett grundark från spelets etablerade fakta
     (namnet Eevan avslöjades av spelaren själv vid turn 59; 'Faelyndra'
      var en Guardian-hallucination som aldrig användes av spelaren/DM)
  3. Bevarar ALL Guardian-tillväxtdata (updates, xp, death_saves, spells,
     nuvarande HP) — inget narrativt ändras
  4. Appendar en admin-notis till transcriptet så spelaren ser vad som hände

Körs INUTI containern: docker exec loreweavers-cauldron python3 /app/backend/scripts/fix_daddy_character.py
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(os.environ.get("DATA_DIR", "/app/backend/data"))
USER = "daddy"
CID = "425d34f9e222"
CDIR = BASE / "campaigns" / USER / CID
STATE = CDIR / "state.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    if not STATE.exists():
        print("ERROR: state.json hittades inte:", STATE)
        return 1

    # ── 1. Backup ──
    backup_dir = CDIR / "backups" / ("patch-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(STATE, backup_dir / "state.json")
    for tf in (CDIR / "transcripts").glob("session-*.jsonl"):
        shutil.copy(tf, backup_dir / tf.name)
    print("backup →", backup_dir)

    # ── 2. Läs state, plocka ut Guardian-tillväxtdata ──
    state = json.loads(STATE.read_text())
    old = state.get("character") or {}
    preserved = {k: old[k] for k in ("updates", "xp", "death_saves", "spells") if k in old}
    hp_current = int((old.get("hp") or {}).get("current", 1) or 1)

    # ── 3. Rekonstruera grundarket (level 2: xp.next_level=900 ⇒ passerat 300) ──
    char = {
        "name": "Eevan",
        "race": "Human",
        "class": "Rogue",
        "alignment": "Chaotic Neutral",
        "background": "Charlatan — a runaway thief hiding in the Gilded Haze",
        "level": 2,
        "abilities": {
            "STR": {"score": 10, "mod": 0},
            "DEX": {"score": 16, "mod": 3},
            "CON": {"score": 12, "mod": 1},
            "INT": {"score": 13, "mod": 1},
            "WIS": {"score": 11, "mod": 0},
            "CHA": {"score": 15, "mod": 2},
        },
        # HP max från CON (8 + 1 per nivå); current orörd — Guardian äger den
        "hp": {"current": hp_current, "max": 13, "temp": 0},
        "ac": 14,          # leather + DEX
        "initiative": 3,
        "proficiency": 2,
        "perception": 10,
        "max_weight_lbs": 150,  # STR 10 × 15
        "saves": [{"name": "DEX", "prof": True}, {"name": "INT", "prof": True}],
        "traits": ["Sneak Attack", "Cunning Action"],
        "gear": "Thieves' tools · Hooded brass lantern · Wool cloak",
        "story": (
            "A thief on the run, hiding in the Gilded Haze after stealing Agent Smiths' "
            "most precious merchandise — a debt that ties him to his past, and to a woman "
            "left behind, the one with sadness in her eyes. Bound to a living brass compass "
            "that shows its holder what they truly seek. Vexia calls him Mirror-Man; his "
            "real name — Eevan — is known only to Vexia and Morwen. Survived Leeren's iron "
            "vault on a compass and a lie."
        ),
    }
    # Guardian-tillväxtdata läggs tillbaka ovanpå grundarket
    char.update(preserved)
    state["character"] = char

    # ── 4. Atomär skrivning ──
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    os.replace(tmp, STATE)
    print("state.json restored — name:", char["name"], "| level:", char["level"],
          "| hp:", char["hp"], "| preserved keys:", sorted(preserved.keys()))

    # ── 5. Admin-notis i transcriptet (renderas som DM-meddelande i chatten) ──
    tfile = CDIR / "transcripts" / f"session-{state['meta'].get('session_count', 1):03d}.jsonl"
    entry = {
        "role": "assistant",
        "content": (
            "*🔧 Emergency patch applied — courtesy of Web Admin and Hästis [AI]. "
            "Your character sheet has been restored; nothing else has changed. "
            "The story continues exactly where you left it.*"
        ),
        "ts": now(),
    }
    with open(tfile, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("transcript note appended →", tfile.name)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
