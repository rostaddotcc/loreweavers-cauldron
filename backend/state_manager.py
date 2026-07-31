"""
Mörkrets Rike — Campaign State Manager
========================================
JSON-filer under data/campaigns/{user}/{campaign_id}/.
Varje kampanj: state.json + transcripts/ + summaries/.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
CAMPAIGNS_DIR = DATA_DIR / "campaigns"
VAULTS_DIR = DATA_DIR / "vaults"

SUMMARY_INTERVAL = 20  # Var 20:e tur → sammanfattning (Nivå 1: scen)
CHAPTER_EVERY = 5      # Var 5:e scen-sammanfattning → kapitel (Nivå 2)
ARC_EVERY = 3          # Var 3:e kapitel → kampanjbåge (Nivå 3)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state(campaign_id: str, user: str) -> dict:
    """Tomt kampanjtillstånd enligt state-schema.json."""
    return {
        "meta": {
            "campaign_id": campaign_id,
            "campaign_name": "Ett svenskt D&D-äventyr",
            "user": user,
            "created": _now(),
            "last_updated": _now(),
            "turn_count": 0,
            "session_count": 1,
        },
        "character": {},
        "inventory": [],
        "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
        "npcs": [],
        "quests": [],
        "world": {
            "current_location": "",
            "visited_locations": [],
            "time": "",
            "weather": "",
        },
        "lore": [],
        "pinned_facts": [],
        "locations": [],
        "images": [],
    }


class CampaignStore:
    """Hanterar en användares kampanjer på disk."""

    def __init__(self):
        CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user: str) -> Path:
        return CAMPAIGNS_DIR / user

    def _active_file(self, user: str) -> Path:
        """Pekarfil: innehåller campaign_id för den aktiva kampanjen."""
        return self._user_dir(user) / ".active_campaign"

    def _campaign_dir(self, user: str, campaign_id: str) -> Path:
        return self._user_dir(user) / campaign_id

    def _state_path(self, user: str, campaign_id: str) -> Path:
        return self._campaign_dir(user, campaign_id) / "state.json"

    def _transcripts_dir(self, user: str, campaign_id: str) -> Path:
        return self._campaign_dir(user, campaign_id) / "transcripts"

    def _summaries_dir(self, user: str, campaign_id: str) -> Path:
        return self._campaign_dir(user, campaign_id) / "summaries"

    def _saves_dir(self, user: str, campaign_id: str) -> Path:
        return self._campaign_dir(user, campaign_id) / "saves"

    # ── CRUD ──

    def create(self, user: str, name: str = "", language: str = "en") -> dict:
        """Skapa ny kampanj. Sätter den som aktiv. Returnerar state."""
        campaign_id = uuid.uuid4().hex[:12]
        cdir = self._campaign_dir(user, campaign_id)
        cdir.mkdir(parents=True, exist_ok=True)
        self._transcripts_dir(user, campaign_id).mkdir(exist_ok=True)
        self._summaries_dir(user, campaign_id).mkdir(exist_ok=True)

        state = _default_state(campaign_id, user)
        if name:
            state["meta"]["campaign_name"] = name
        if language:
            state["meta"]["language"] = language
        self.save(state)
        # Sätt som aktiv kampanj
        self._set_active_pointer(user, campaign_id)
        return state

    def _set_active_pointer(self, user: str, campaign_id: str) -> None:
        """Skriv pekarfilen för aktiv kampanj."""
        udir = self._user_dir(user)
        udir.mkdir(parents=True, exist_ok=True)
        (udir / ".active_campaign").write_text(campaign_id)

    def _get_active_pointer(self, user: str) -> str | None:
        """Läs pekarfilen för aktiv kampanj."""
        f = self._active_file(user)
        if f.exists():
            cid = f.read_text().strip()
            if cid and self._state_path(user, cid).exists():
                return cid
        return None

    def get(self, user: str, campaign_id: str | None = None) -> dict | None:
        """Hämta en specifik kampanj eller den aktiva (via pekarfil)."""
        if campaign_id:
            sp = self._state_path(user, campaign_id)
            if not sp.exists():
                return None
            try:
                with open(sp) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return None
        # Ingen campaign_id → använd pekarfilen (aktiv kampanj)
        active_id = self._get_active_pointer(user)
        if active_id:
            return self.get(user, active_id)
        # Fallback: senast uppdaterad (bakåtkompatibilitet)
        udir = self._user_dir(user)
        if not udir.exists():
            return None
        candidates = []
        for cdir in udir.iterdir():
            sp = cdir / "state.json"
            if sp.exists():
                try:
                    with open(sp) as f:
                        state = json.load(f)
                    candidates.append(state)
                except (json.JSONDecodeError, OSError):
                    continue
        if not candidates:
            return None
        candidates.sort(key=lambda s: s["meta"].get("last_updated", ""), reverse=True)
        return candidates[0]

    def list_campaigns(self, user: str) -> list[dict]:
        """Lista alla kampanjer för en användare (senast uppdaterad först)."""
        udir = self._user_dir(user)
        if not udir.exists():
            return []
        results = []
        for cdir in udir.iterdir():
            sp = cdir / "state.json"
            if not sp.exists():
                continue
            try:
                with open(sp) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            meta = state.get("meta", {})
            char = state.get("character", {})
            world = state.get("world", {})
            results.append({
                "campaign_id": meta.get("campaign_id", ""),
                "name": meta.get("campaign_name", "Namnlös kampanj"),
                "character_name": char.get("name", ""),
                "character_icon": char.get("icon", "🎭"),
                "level": char.get("level", 1),
                "turn_count": meta.get("turn_count", 0),
                "last_updated": meta.get("last_updated", ""),
                "created": meta.get("created", ""),
                "location": world.get("current_location", ""),
                "language": meta.get("language", "en"),
            })
        results.sort(key=lambda c: c.get("last_updated", ""), reverse=True)
        return results

    def total_turns(self, user: str) -> int:
        """Summan av alla kampanjers turn_count för en användare (snabb koll utan transkript)."""
        total = 0
        for c in self.list_campaigns(user):
            total += int(c.get("turn_count", 0) or 0)
        return total

    def delete(self, user: str, campaign_id: str) -> bool:
        """Radera en specifik kampanj. Returnerar True om något raderades."""
        import shutil
        cdir = self._campaign_dir(user, campaign_id)
        if not cdir.exists():
            return False
        shutil.rmtree(cdir)
        return True

    def set_active(self, user: str, campaign_id: str) -> dict | None:
        """Markera en kampanj som aktiv (pekarfil + last_updated)."""
        state = self.get(user, campaign_id)
        if not state:
            return None
        self._set_active_pointer(user, campaign_id)
        state["meta"]["last_updated"] = _now()
        self.save(state)
        return state

    def save(self, state: dict) -> None:
        """Spara state till disk."""
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        state["meta"]["last_updated"] = _now()
        sp = self._state_path(user, cid)
        sp.parent.mkdir(parents=True, exist_ok=True)
        with open(sp, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # ── Transcript ──

    def append_message(self, state: dict, role: str, content: str, meta: dict | None = None) -> dict:
        """Lägg till meddelande i transcript. Uppdaterar turn_count vid user-msg."""
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        tdir = self._transcripts_dir(user, cid)
        tdir.mkdir(parents=True, exist_ok=True)

        session = state["meta"].get("session_count", 1)
        tfile = tdir / f"session-{session:03d}.jsonl"

        entry = {"role": role, "content": content, "ts": _now()}
        if meta:
            entry["meta"] = meta
        with open(tfile, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if role == "user":
            state["meta"]["turn_count"] = state["meta"].get("turn_count", 0) + 1

        return state

    def load_transcript(self, state: dict, last_n: int = 20) -> list[dict]:
        """Läs de senaste N meddelandena från transcript."""
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        tdir = self._transcripts_dir(user, cid)
        if not tdir.exists():
            return []

        entries = []
        for tfile in sorted(tdir.glob("session-*.jsonl")):
            with open(tfile) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return entries[-last_n:]

    def load_transcript_by_tokens(
        self, state: dict, budget_tokens: int = 6000, min_messages: int = 8
    ) -> list[dict]:
        """Token-baserat glidande fönster — fyll bakifrån tills budgeten är slut.

        Tokenuppskattning: len(content) // 3 (fungerar bra för svensk text).
        Behåller alltid minst min_messages meddelanden oavsett budget.
        """
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        tdir = self._transcripts_dir(user, cid)
        if not tdir.exists():
            return []

        entries = []
        for tfile in sorted(tdir.glob("session-*.jsonl")):
            with open(tfile) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        if not entries:
            return []

        # Fyll bakifrån tills tokenbudgeten tar slut
        selected: list[dict] = []
        tokens_used = 0
        for entry in reversed(entries):
            content = entry.get("content", "")
            est_tokens = max(1, len(content) // 3)
            if tokens_used + est_tokens > budget_tokens and len(selected) >= min_messages:
                break
            selected.append(entry)
            tokens_used += est_tokens

        selected.reverse()
        return selected

    # ── Summaries ──

    def maybe_summarize(self, state: dict) -> bool:
        """Returnerar True om turn_count är en multipel av SUMMARY_INTERVAL."""
        tc = state["meta"].get("turn_count", 0)
        return tc > 0 and tc % SUMMARY_INTERVAL == 0

    def save_summary(self, state: dict, summary_text: str) -> None:
        """Spara sammanfattning till summaries/."""
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        sdir = self._summaries_dir(user, cid)
        sdir.mkdir(parents=True, exist_ok=True)

        tc = state["meta"].get("turn_count", 0)
        sfile = sdir / f"summary-turn-{tc:04d}.json"
        with open(sfile, "w") as f:
            json.dump(
                {"turn": tc, "text": summary_text, "created": _now()},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def load_summaries(self, state: dict, last_n: int = 3) -> list[dict]:
        """Läs de senaste N sammanfattningarna (Nivå 1: scen)."""
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        sdir = self._summaries_dir(user, cid)
        if not sdir.exists():
            return []
        files = sorted(sdir.glob("summary-*.json"))
        results = []
        for sf in files[-last_n:]:
            try:
                with open(sf) as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    # ── Hierarkiska sammanfattningar (Nivå 2 & 3) ──

    def count_scene_summaries(self, state: dict) -> int:
        """Räkna antal scen-sammanfattningar (Nivå 1)."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        if not sdir.exists():
            return 0
        return len(list(sdir.glob("summary-*.json")))

    def maybe_chapter(self, state: dict) -> bool:
        """True om antalet scen-sammanfattningar är en multipel av CHAPTER_EVERY."""
        n = self.count_scene_summaries(state)
        return n > 0 and n % CHAPTER_EVERY == 0

    def save_chapter_summary(self, state: dict, chapter_text: str) -> None:
        """Spara kapitel-sammanfattning (Nivå 2) som chapter-NNN.json."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        sdir.mkdir(parents=True, exist_ok=True)
        existing = sorted(sdir.glob("chapter-*.json"))
        num = len(existing) + 1
        cfile = sdir / f"chapter-{num:03d}.json"
        with open(cfile, "w") as f:
            json.dump(
                {"chapter": num, "text": chapter_text, "created": _now()},
                f, ensure_ascii=False, indent=2,
            )

    def count_chapter_summaries(self, state: dict) -> int:
        """Räkna antal kapitel-sammanfattningar (Nivå 2)."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        if not sdir.exists():
            return 0
        return len(list(sdir.glob("chapter-*.json")))

    def maybe_arc(self, state: dict) -> bool:
        """True om antalet kapitel är en multipel av ARC_EVERY."""
        n = self.count_chapter_summaries(state)
        return n > 0 and n % ARC_EVERY == 0

    def save_campaign_arc(self, state: dict, arc_text: str) -> None:
        """Spara kampanjbåge (Nivå 3) som campaign-arc-NNN.json."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        sdir.mkdir(parents=True, exist_ok=True)
        existing = sorted(sdir.glob("campaign-arc-*.json"))
        num = len(existing) + 1
        afile = sdir / f"campaign-arc-{num:03d}.json"
        with open(afile, "w") as f:
            json.dump(
                {"arc": num, "text": arc_text, "created": _now()},
                f, ensure_ascii=False, indent=2,
            )

    def load_chapters(self, state: dict, last_n: int = 2) -> list[dict]:
        """Läs de senaste N kapitel-sammanfattningarna (Nivå 2)."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        if not sdir.exists():
            return []
        files = sorted(sdir.glob("chapter-*.json"))
        results = []
        for cf in files[-last_n:]:
            try:
                with open(cf) as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def load_campaign_arcs(self, state: dict, last_n: int = 1) -> list[dict]:
        """Läs de senaste N kampanjbågarna (Nivå 3)."""
        sdir = self._summaries_dir(state["meta"]["user"], state["meta"]["campaign_id"])
        if not sdir.exists():
            return []
        files = sorted(sdir.glob("campaign-arc-*.json"))
        results = []
        for af in files[-last_n:]:
            try:
                with open(af) as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    # ── Export helpers ──

    def get_campaign_dir(self, state: dict) -> Path:
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        return self._campaign_dir(user, cid)

    def get_transcripts_dir(self, state: dict) -> Path:
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        return self._transcripts_dir(user, cid)

    def get_summaries_dir(self, state: dict) -> Path:
        user = state["meta"]["user"]
        cid = state["meta"]["campaign_id"]
        return self._summaries_dir(user, cid)


class CharacterVault:
    """Karaktärsvalvet — sparade hjältar som överlever kampanjslut.

    Varje användare har en vault/ med en JSON-fil per sparad karaktär.
    Karaktärer kan återanvändas i nya kampanjer.
    """

    def __init__(self):
        VAULTS_DIR.mkdir(parents=True, exist_ok=True)

    def _vault_dir(self, user: str) -> Path:
        d = VAULTS_DIR / user
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, user: str, character: dict, campaign_name: str = "") -> dict:
        """Spara karaktär i valvet. Returnerar vault-posten."""
        char_id = uuid.uuid4().hex[:10]
        entry = {
            "id": char_id,
            "character": character,
            "campaign_name": campaign_name,
            "saved_at": _now(),
        }
        path = self._vault_dir(user) / f"{char_id}.json"
        with open(path, "w") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return entry

    def list(self, user: str) -> list[dict]:
        """Lista alla sparade karaktärer (senast sparad först)."""
        entries = []
        for p in self._vault_dir(user).glob("*.json"):
            try:
                with open(p) as f:
                    entries.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        entries.sort(key=lambda e: e.get("saved_at", ""), reverse=True)
        return entries

    def get(self, user: str, char_id: str) -> dict | None:
        """Hämta en specifik karaktär ur valvet."""
        path = self._vault_dir(user) / f"{char_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, user: str, char_id: str) -> bool:
        """Radera en karaktär ur valvet."""
        path = self._vault_dir(user) / f"{char_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True
