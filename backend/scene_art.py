"""Scene art — opt-in illustration of the scene the player just read (2026-10-27).

Rostads beslut: bilden målas NÄR SPELAREN BER OM DEN, aldrig automatiskt. Ett
automatiskt beat-flöde (StoryRoll/F&F-modellen) äter hela dygnstaket på tio
meddelanden och ger bilder på scener ingen brydde sig om.

Kontrakt:
  * Prompten byggs ur STATET (plats, tid, väder) + den narration spelaren
    klickade på — inte ur spelarens fantasi, så bilden matchar det som hände.
  * ALDRIG statistik i prompten (HP/AC/tärningar/turn-tal): siffror i en
    bildprompt blir klotter i bilden. Samma regel som avatar-prompten.
  * Ingen karaktärsnamn i prompten: målade namn blir text i bilden.
  * En fast stil-suffix så alla scener i en kampanj ser ut som samma värld.

Modulen är ren (ingen IO) så promptbygget kan testas utan API-nycklar.
"""
from __future__ import annotations

import re

# En stil för hela världen — byt här om tonen ska ändras, aldrig per anrop.
SCENE_STYLE = (
    "dark fantasy oil painting, muted ember and cold ash palette, "
    "cinematic wide shot, volumetric light, painterly brushwork, "
    "no text, no watermark, no frame"
)

MAX_EXCERPT = 420
MAX_PROMPT = 490

# Siffror som hör till spelet (HP 12/20, AC 15, 3 turns) — bort ur prompten.
_STAT_RE = re.compile(
    r"\b(?:hp|health)\s*[:=]?\s*\d+(?:\s*/\s*\d+)?"      # HP 12/20 · HP 12
    r"|\b\d+\s*/\s*\d+\s*(?:hp|health)\b"                 # 12/20 HP
    r"|\bAC\s*[:=]?\s*\d+\b"                              # AC 15
    r"|\b\d+\s*(?:turns?|turer)\b"                        # 3 turns
    r"|\b\d+\s*(?:damage|skada|dmg)\b"                    # 7 damage
    r"|\b\d+\s*(?:xp|guld|gold|gp|sp|cp)\b",              # 120 xp, 15 gp
    re.I,
)
_TAG_RE = re.compile(r"\[[A-ZÅÄÖ_]{2,}:[^\]]*\]")          # [KAST:...] [STRID:...]
_CODE_RE = re.compile(r"```.*?```", re.S)
_MD_RE = re.compile(r"[*_#>`~|]+")


def clean_excerpt(text: str, limit: int = MAX_EXCERPT) -> str:
    """Narration → en ren scenbeskrivning för bildprompten."""
    t = _CODE_RE.sub(" ", str(text or ""))
    t = _TAG_RE.sub(" ", t)
    t = _MD_RE.sub(" ", t)
    t = _STAT_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        cut = t[:limit]
        # Klipp vid meningsslut om det finns nära slutet, annars vid ordgräns.
        dot = cut.rfind(". ")
        if dot > limit * 0.55:
            t = cut[: dot + 1]
        else:
            t = cut.rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
    return t


def build_scene_prompt(state: dict, excerpt: str = "", lang: str = "en") -> str:
    """State + vald narration → en bildprompt. Tom state ger ändå en giltig prompt."""
    world = (state or {}).get("world") or {}
    where = str(world.get("current_location") or "").strip()
    when = str(world.get("time") or "").strip()
    weather = str(world.get("weather") or "").strip()
    scene = clean_excerpt(excerpt)

    parts: list[str] = []
    if where:
        parts.append(f"Setting: {where}.")
    if when:
        parts.append(f"Moment: {when}.")
    if weather:
        parts.append(f"Weather: {weather}.")
    if scene:
        parts.append(f"Scene: {scene}")
    if not parts:
        # Ingen kampanjdata alls (t.ex. direkt efter skapandet): en ärlig
        # generic i stället för en tom sträng som API:et skulle 400:a på.
        parts.append("Scene: a quiet roadside camp at dusk, a fire, a waiting road.")
    return (" ".join(parts + [SCENE_STYLE]))[:MAX_PROMPT]