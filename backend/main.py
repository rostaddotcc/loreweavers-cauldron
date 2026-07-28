"""
Mörkrets Rike — FastAPI Backend
=================================
LLM-driven D&D Dungeon Master. Alla endpoints under /api/.
"""

import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Cookie, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import create_token, load_users, verify_password, verify_token
from dice import roll as dice_roll
from models import DM_SYSTEM_PROMPT, get_api_key, get_model, list_models_for_frontend
from atmosphere import build_art_prompt, detect_environments
from locations import get_locations_with_travel
from logbook import build_log_prompt
from state_manager import CampaignStore, CharacterVault

app = FastAPI(title="Mörkrets Rike", version="1.0.0")

# ═══════════════════════════════════════
# NPC-parsning + Äventyrsöppningar
# ═══════════════════════════════════════
import random

NPC_PATTERN = re.compile(r'\[NPC:([^|]+)\|([^|]+)\|([^\]]+)\]')
KAST_PATTERN = re.compile(r'\[KAST:\s*([^\]|]+)(?:\|([^\]]+))?\]')

NPC_COLORS = ['#8b5fd4', '#d4691e', '#7aa35e', '#5e9aa3', '#d43a4d', '#c9a227', '#a8b2c0', '#b06fd4']
NPC_ICONS = ['🧙', '⚔️', '🏹', '🛡️', '🎭', '👻', '🐺', '🦉', '💀', '🔮', '🗡️', '🌙']

OPENING_STYLES = [
    ('meeting', 'Äventyret börjar med att spelaren möter en intressant NPC. Ge dem ett namn, en personlighet och en anledning att vara där.'),
    ('alone', 'Spelaren är helt ensam. Beskriv omgivningen atmosfäriskt. Låt spelaren utforska och upptäcka saker i sin egen takt.'),
    ('in_media_res', 'Äventyret börjar mitt i en pågående händelse — en strid, en flykt, ett brinnande hus. Kasta spelaren rakt in.'),
    ('awakening', 'Spelaren vaknar på en okänd plats. De vet inte hur de hamnade där. Beskriv vad de ser, hör och känner.'),
    ('summoned', 'Spelaren har kallats till en plats av någon med ett uppdrag eller ett erbjudande. Vem kallade dem, och varför?'),
]


def _parse_npcs(text: str) -> tuple[str, list[dict]]:
    """Extrahera [NPC:namn|roll|relation]-taggar ur DM-svar."""
    npcs = []
    for i, m in enumerate(NPC_PATTERN.finditer(text)):
        name, role, relation = m.group(1).strip(), m.group(2).strip(), m.group(3).strip().lower()
        if relation not in ('allierad', 'neutral', 'fiende', 'okänd'):
            relation = 'okänd'
        npcs.append({
            'name': name, 'role': role, 'relation': relation,
            'color': NPC_COLORS[i % len(NPC_COLORS)],
            'icon': NPC_ICONS[i % len(NPC_ICONS)],
            'notes': '', 'alive': True,
        })
    clean = NPC_PATTERN.sub('', text).strip()
    return clean, npcs


def _parse_roll_requests(text: str) -> tuple[str, list[dict]]:
    """Extrahera [KAST: 1d20+4 | SMIDIGHET för att smyga]-taggar ur DM-svar."""
    rolls = []
    for m in KAST_PATTERN.finditer(text):
        notation = m.group(1).strip()
        label = (m.group(2) or '').strip()
        rolls.append({'notation': notation, 'label': label or notation})
    clean = KAST_PATTERN.sub('', text).strip()
    return clean, rolls


# ═══════════════════════════════════════
# Mekaniska taggar — påverka spelstate
# ═══════════════════════════════════════

# D&D 5e XP-trösklar för level-up
XP_THRESHOLDS = [0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
                 85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000,
                 305000, 355000]

# Regex-mönster för mekaniska taggar
_MECH_PATTERNS = {
    'SKADA':           re.compile(r'\[SKADA:(\d+)\]'),
    'HELA':            re.compile(r'\[HELA:(\d+)\]'),
    'XP':              re.compile(r'\[XP:(\d+)\]'),
    'GULD':            re.compile(r'\[GULD:(-?\d+)\]'),
    'FÖREMÅL':         re.compile(r'\[FÖREMÅL:([^|\]]+)(?:\|([^|\]]+))?(?:\|([^\]]+))?\]'),
    'QUEST':           re.compile(r'\[QUEST:([^|\]]+)(?:\|([^|\]]+))?(?:\|([^\]]+))?\]'),
    'QUEST_SLUTFÖRD':  re.compile(r'\[QUEST_SLUTFÖRD:([^\]]+)\]'),
    'QUEST_MISSLYCKAD': re.compile(r'\[QUEST_MISSLYCKAD:([^\]]+)\]'),
    'KONSEKVENS':      re.compile(r'\[KONSEKVENS:([^\]]+)\]'),
    'NPC_DÖD':         re.compile(r'\[NPC_DÖD:([^\]]+)\]'),
    'PLATS':           re.compile(r'\[PLATS:([^\]]+)\]'),
    'TID':             re.compile(r'\[TID:([^\]]+)\]'),
}


def _parse_mechanical_tags(text: str, state: dict) -> tuple[str, dict, list[dict]]:
    """
    Hitta och ta bort alla mekaniska taggar ur DM-svaret.
    Uppdaterar state och returnerar (clean_text, state, effects_list).
    """
    effects: list[dict] = []

    # SKADA — minska HP
    for m in _MECH_PATTERNS['SKADA'].finditer(text):
        amount = int(m.group(1))
        char = state.setdefault('character', {})
        hp = char.setdefault('hp', {'current': 10, 'max': 10, 'temp': 0})
        hp['current'] = max(0, hp.get('current', 0) - amount)
        effects.append({'type': 'skada', 'value': amount})

    # HELA — öka HP
    for m in _MECH_PATTERNS['HELA'].finditer(text):
        amount = int(m.group(1))
        char = state.setdefault('character', {})
        hp = char.setdefault('hp', {'current': 10, 'max': 10, 'temp': 0})
        hp['current'] = min(hp.get('max', 10), hp.get('current', 0) + amount)
        effects.append({'type': 'hela', 'value': amount})

    # XP — ge erfarenhet + level-up
    for m in _MECH_PATTERNS['XP'].finditer(text):
        amount = int(m.group(1))
        char = state.setdefault('character', {})
        xp = char.setdefault('xp', {'current': 0, 'next_level': 300})
        xp['current'] = xp.get('current', 0) + amount
        effects.append({'type': 'xp', 'value': amount})
        # Level-up check
        level = char.get('level', 1)
        while level < len(XP_THRESHOLDS) and xp['current'] >= XP_THRESHOLDS[level]:
            level += 1
            char['level'] = level
            if level < len(XP_THRESHOLDS):
                xp['next_level'] = XP_THRESHOLDS[level]
            effects.append({'type': 'level_up', 'value': level})

    # GULD — lägg till/ta bort guld
    for m in _MECH_PATTERNS['GULD'].finditer(text):
        amount = int(m.group(1))
        currency = state.setdefault('currency', {'pp': 0, 'gp': 0, 'ep': 0, 'sp': 0, 'cp': 0})
        currency['gp'] = currency.get('gp', 0) + amount
        effects.append({'type': 'guld', 'value': amount})

    # FÖREMÅL — lägg till i inventariet
    for m in _MECH_PATTERNS['FÖREMÅL'].finditer(text):
        name = m.group(1).strip()
        item_type = (m.group(2) or 'Annat').strip()
        rarity = (m.group(3) or 'normal').strip()
        inv = state.setdefault('inventory', [])
        inv.append({
            'id': f"tag-{len(inv)}",
            'name': name,
            'type': item_type,
            'qty': 1,
            'weight': 0,
            'equipped': False,
            'rarity': rarity,
            'description': '',
        })
        effects.append({'type': 'föremål', 'value': name})

    # QUEST — skapa nytt uppdrag
    for m in _MECH_PATTERNS['QUEST'].finditer(text):
        name = m.group(1).strip()
        desc = (m.group(2) or '').strip()
        reward = (m.group(3) or '').strip()
        quests = state.setdefault('quests', [])
        quests.append({
            'name': name,
            'description': desc,
            'reward': reward,
            'status': 'aktiv',
        })
        effects.append({'type': 'quest', 'value': name})

    # QUEST_SLUTFÖRD
    for m in _MECH_PATTERNS['QUEST_SLUTFÖRD'].finditer(text):
        name = m.group(1).strip()
        for q in state.get('quests', []):
            if q.get('name', '').lower() == name.lower():
                q['status'] = 'slutförd'
                break
        effects.append({'type': 'quest_slutförd', 'value': name})

    # QUEST_MISSLYCKAD
    for m in _MECH_PATTERNS['QUEST_MISSLYCKAD'].finditer(text):
        name = m.group(1).strip()
        for q in state.get('quests', []):
            if q.get('name', '').lower() == name.lower():
                q['status'] = 'misslyckad'
                break
        effects.append({'type': 'quest_misslyckad', 'value': name})

    # KONSEKVENS — permanent världsförändring → lore
    for m in _MECH_PATTERNS['KONSEKVENS'].finditer(text):
        desc = m.group(1).strip()
        state.setdefault('lore', []).append(desc)
        effects.append({'type': 'konsekvens', 'value': desc})

    # NPC_DÖD — markera NPC som död
    for m in _MECH_PATTERNS['NPC_DÖD'].finditer(text):
        name = m.group(1).strip()
        for npc in state.get('npcs', []):
            if npc.get('name', '').lower() == name.lower():
                npc['alive'] = False
                break
        effects.append({'type': 'npc_död', 'value': name})

    # PLATS — uppdatera nuvarande plats
    for m in _MECH_PATTERNS['PLATS'].finditer(text):
        name = m.group(1).strip()
        world = state.setdefault('world', {})
        world['current_location'] = name
        visited = world.setdefault('visited_locations', [])
        if name not in visited:
            visited.append(name)
        effects.append({'type': 'plats', 'value': name})

    # TID — uppdatera tid/väder
    for m in _MECH_PATTERNS['TID'].finditer(text):
        desc = m.group(1).strip()
        world = state.setdefault('world', {})
        world['time'] = desc
        effects.append({'type': 'tid', 'value': desc})

    # Ta bort alla taggar ur texten
    clean = text
    for pattern in _MECH_PATTERNS.values():
        clean = pattern.sub('', clean)
    # Städa upp dubbla blanksteg/rader som blir kvar
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

    return clean, state, effects

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = CampaignStore()
vault = CharacterVault()

COOKIE_NAME = "morkrets_token"

# Atmosfär-subagent: snabb modell för ASCII-art
ATMOSPHERE_MODEL = os.getenv("ATMOSPHERE_MODEL", "qwen3.6-flash")


# ═══════════════════════════════════════
# Pydantic-modeller
# ═══════════════════════════════════════


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str
    model_id: str


class CharacterRequest(BaseModel):
    prompt: str
    model_id: str


class DiceRequest(BaseModel):
    notation: str


class VaultSaveRequest(BaseModel):
    character: dict


class VaultUseRequest(BaseModel):
    char_id: str


# ═══════════════════════════════════════
# Auth-hjälp
# ═══════════════════════════════════════


def _get_current_user(morkrets_token: str | None) -> dict:
    """Validera cookie → returnerar {sub, role}. 401 om ogiltig."""
    if not morkrets_token:
        raise HTTPException(401, "Ej inloggad")
    payload = verify_token(morkrets_token)
    if not payload:
        raise HTTPException(401, "Ogiltig eller utgången session")
    return payload


# ═══════════════════════════════════════
# LLM-anrop (OpenAI-kompatibelt via httpx)
# ═══════════════════════════════════════


async def _call_llm(
    model_id: str,
    messages: list[dict],
    temperature: float = 0.8,
    max_tokens: int = 1024,
) -> str:
    """Anropa vald modell via OpenAI-kompatibelt /chat/completions."""
    config = get_model(model_id)
    api_key = get_api_key(config)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": config.api_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    url = f"{config.base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise HTTPException(
                502, f"LLM-fel ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    """Extrahera JSON från LLM-svar (kan vara inbäddat i markdown)."""
    # Prova direkt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Prova ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Hitta första { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("Kunde inte extrahera JSON ur LLM-svaret")


# ═══════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════


@app.post("/api/login")
async def login(req: LoginRequest, response: Response):
    users = load_users()
    user = users.get(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Fel användarnamn eller lösenord")

    token = create_token(req.username, user["role"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "username": req.username, "role": user["role"]}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/me")
async def me(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    return {"username": payload["sub"], "role": payload.get("role", "player")}


# ═══════════════════════════════════════
# MODELS
# ═══════════════════════════════════════


@app.get("/api/models")
async def models(morkrets_token: str | None = Cookie(None)):
    _get_current_user(morkrets_token)
    return list_models_for_frontend()


# ═══════════════════════════════════════
# DICE
# ═══════════════════════════════════════


@app.post("/api/dice")
async def dice(req: DiceRequest, morkrets_token: str | None = Cookie(None)):
    _get_current_user(morkrets_token)
    try:
        return dice_roll(req.notation)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════
# CAMPAIGN CRUD
# ═══════════════════════════════════════


@app.post("/api/campaign")
async def create_campaign(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    existing = store.get(username)
    if existing:
        raise HTTPException(
            409,
            detail={
                "message": "Du har redan en aktiv kampanj",
                "campaign": {
                    "id": existing["meta"]["campaign_id"],
                    "name": existing["meta"]["campaign_name"],
                    "turn_count": existing["meta"]["turn_count"],
                    "created": existing["meta"]["created"],
                },
            },
        )

    state = store.create(username)
    # Slumpa en äventyrsöppning
    style_key, style_desc = random.choice(OPENING_STYLES)
    state["meta"]["opening_style"] = style_desc
    state["meta"]["opening_key"] = style_key
    store.save(state)
    return {"ok": True, "campaign_id": state["meta"]["campaign_id"], "opening": style_key}


@app.get("/api/campaign")
async def get_campaign(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")
    return state


@app.delete("/api/campaign")
async def delete_campaign(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    deleted = store.delete(payload["sub"])
    if not deleted:
        raise HTTPException(404, "Ingen kampanj att radera")
    return {"ok": True, "message": "Kampanjen har avslutats och raderats"}


# ═══════════════════════════════════════
# CHAT
# ═══════════════════════════════════════


def _build_system_prompt(state: dict) -> str:
    """Bygg systemprompt med kampanjkontext."""
    parts = [DM_SYSTEM_PROMPT]

    # Karaktär
    char = state.get("character")
    if char and char.get("name"):
        parts.append(f"\n## Spelarens karaktär\n{json.dumps(char, ensure_ascii=False, indent=1)}")

    # Värld
    world = state.get("world", {})
    if world.get("current_location"):
        parts.append(f"\n## Värld\nPlats: {world['current_location']}")
        if world.get("time"):
            parts.append(f"Tid: {world['time']}")
        if world.get("weather"):
            parts.append(f"Väder: {world['weather']}")

    # NPCs
    npcs = state.get("npcs", [])
    if npcs:
        npc_str = "; ".join(
            f"{n.get('name', '?')} ({n.get('role', '?')}, {n.get('relation', '?')})"
            for n in npcs[:10]
        )
        parts.append(f"\n## Kända NPC:er\n{npc_str}")

    # Quests
    quests = state.get("quests", [])
    active = [q for q in quests if q.get("status") == "aktiv"]
    if active:
        q_str = "; ".join(q.get("name", "?") for q in active[:5])
        parts.append(f"\n## Aktiva uppdrag\n{q_str}")

    # Äventyrsöppning (bara vid första draget)
    opening = state.get("meta", {}).get("opening_style", "")
    if opening and state.get("meta", {}).get("turn_count", 0) == 0:
        parts.append(f"\n## Äventyrsöppning (första draget)\n{opening}")

    return "\n".join(parts)


@app.post("/api/chat")
async def chat(req: ChatRequest, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj — skapa en först")

    # Lägg till spelarens meddelande
    state = store.append_message(state, "user", req.message)

    # Bygg meddelandelista
    messages = [{"role": "system", "content": _build_system_prompt(state)}]

    # Lägg till senaste sammanfattningar som kontext
    summaries = store.load_summaries(state, last_n=2)
    for s in summaries:
        messages.append(
            {"role": "system", "content": f"[Sammanfattning vid tur {s['turn']}]: {s['text']}"}
        )

    # Lägg till recent transcript
    transcript = store.load_transcript(state, last_n=16)
    for entry in transcript:
        messages.append({"role": entry["role"], "content": entry["content"]})

    # Anropa LLM
    try:
        reply = await _call_llm(req.model_id, messages)
    except (ValueError, RuntimeError, HTTPException):
        # Trött DM — orkar inte just nu
        reply = random.choice([
            "*Dungeon Master gäspar tungt och lägger ifrån sig tärningarna.*\n\nJag är trött, vi spelar en annan dag. Mörkret vilar... men det glömmer aldrig.",
            "*En suck ekar genom mörkret.*\n\nInte ens en Dungeon Master kan vara vaken jämt. Kom tillbaka när skuggorna är längre.",
            "*Dungeon Master blundar och lutar sig mot bordet.*\n\nI'm tired... let's play later. Äventyret väntar.",
        ])
        # Spara och returnera direkt utan parsning
        state = store.append_message(state, "assistant", reply)
        store.save(state)
        return {
            "reply": reply,
            "turn_count": state["meta"].get("turn_count", 0),
            "summary_generated": False,
            "npcs": [],
            "roll_requests": [],
            "effects": [],
            "ascii_art": None,
            "tired": True,
        }

    # Parsa NPCs och kastbegäran ur svaret
    reply, new_npcs = _parse_npcs(reply)
    reply, roll_requests = _parse_roll_requests(reply)

    # Parsa mekaniska taggar (SKADA, HELA, XP, GULD, etc.)
    reply, state, effects = _parse_mechanical_tags(reply, state)

    # Atmosfär-subagent: generera ASCII-art om miljön triggar
    ascii_art = None
    environments = detect_environments(reply)
    if environments:
        try:
            art_prompt = build_art_prompt(environments[0])
            ascii_art = await _call_llm(
                ATMOSPHERE_MODEL,
                [{"role": "user", "content": art_prompt}],
                temperature=0.9,
                max_tokens=600,
            )
            ascii_art = ascii_art.strip()
            if ascii_art.startswith("```"):
                ascii_art = re.sub(r"^```[a-z]*\n?", "", ascii_art)
                ascii_art = re.sub(r"\n?```$", "", ascii_art)
            ascii_art = ascii_art.strip()
        except Exception:
            ascii_art = None
    for npc in new_npcs:
        existing = {n.get("name", "").lower() for n in state.get("npcs", [])}
        if npc["name"].lower() not in existing:
            state.setdefault("npcs", []).append(npc)

    # Spara DM-svar
    state = store.append_message(state, "assistant", reply)
    store.save(state)

    # Kolla om sammanfattning behövs
    summary_generated = False
    if store.maybe_summarize(state):
        try:
            full_transcript = store.load_transcript(state, last_n=60)
            t_text = "\n".join(
                f"{e['role']}: {e['content']}" for e in full_transcript
            )
            sum_prompt = (
                "Sammanfatta följande D&D-session på svenska. "
                "Fokusera på viktiga händelser, beslut, NPC-möten och konsekvenser. "
                "Max 200 ord.\n\n" + t_text
            )
            summary = await _call_llm(
                req.model_id,
                [{"role": "user", "content": sum_prompt}],
                temperature=0.3,
                max_tokens=512,
            )
            store.save_summary(state, summary)
            summary_generated = True
        except Exception:
            pass  # Sammanfattning är inte kritisk

    return {
        "reply": reply,
        "turn_count": state["meta"]["turn_count"],
        "summary_generated": summary_generated,
        "new_npcs": new_npcs,
        "roll_requests": roll_requests,
        "ascii_art": ascii_art,
        "effects": effects,
    }


# ═══════════════════════════════════════
# CHARACTER GENERATION
# ═══════════════════════════════════════

CHARACTER_PROMPT = """Du är en D&D-karaktärsgenerator. Skapa en karaktär baserad på spelarens beskrivning.

Svara ENDAST med giltig JSON (ingen markdown) med detta schema:
{
  "name": "string",
  "race": "string",
  "class": "string",
  "level": 1,
  "alignment": "string",
  "background": "string",
  "ac": 10,
  "initiative": 0,
  "perception": 10,
  "speed": "30 ft",
  "proficiency": 2,
  "hp": {"current": 10, "max": 10, "temp": 0},
  "spell_slots": {"current": 0, "max": 0},
  "xp": {"current": 0, "next_level": 300},
  "abilities": {
    "STR": {"score": 10, "mod": 0},
    "DEX": {"score": 10, "mod": 0},
    "CON": {"score": 10, "mod": 0},
    "INT": {"score": 10, "mod": 0},
    "WIS": {"score": 10, "mod": 0},
    "CHA": {"score": 10, "mod": 0}
  },
  "traits": [],
  "saves": []
}"""


@app.post("/api/character/generate")
async def generate_character(req: CharacterRequest, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    messages = [
        {"role": "system", "content": CHARACTER_PROMPT},
        {"role": "user", "content": f"Skapa en karaktär: {req.prompt}"},
    ]

    try:
        raw = await _call_llm(req.model_id, messages, temperature=0.7)
        char_data = _extract_json(raw)
    except (ValueError, RuntimeError, HTTPException):
        # Trött DM — generera en enkel fallback-karaktär
        char_data = {
            "name": "Den Trötte Vandraren",
            "race": "Människa",
            "class": "Äventyrare",
            "level": 1,
            "alignment": "Neutral",
            "background": "En trött själ som väntar på bättre tider.",
            "hp": {"current": 10, "max": 10},
            "ac": 10,
            "abilities": {
                "STR": {"score": 10, "mod": 0}, "DEX": {"score": 10, "mod": 0},
                "CON": {"score": 10, "mod": 0}, "INT": {"score": 10, "mod": 0},
                "WIS": {"score": 10, "mod": 0}, "CHA": {"score": 10, "mod": 0},
            },
            "traits": ["Uthållig"],
            "tired": True,
        }

    # Validera löst — se till att grundfält finns
    if not char_data.get("name"):
        char_data["name"] = "Namnlös"
    for field in ("race", "class", "alignment", "background"):
        char_data.setdefault(field, "Okänd")
    char_data.setdefault("level", 1)
    char_data.setdefault("abilities", {})

    state["character"] = char_data
    store.save(state)

    return {"ok": True, "character": char_data}


# ═══════════════════════════════════════
# KARAKTÄRSVALVET
# ═══════════════════════════════════════


@app.post("/api/vault/save")
async def vault_save(req: VaultSaveRequest, morkrets_token: str | None = Cookie(None)):
    """Spara en karaktär i valvet (överlever kampanjslut)."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    char = req.character
    if not char or not char.get("name"):
        raise HTTPException(400, "Karaktären saknar namn")

    # Hämta kampanjnamn om det finns en aktiv kampanj
    state = store.get(username)
    campaign_name = state["meta"].get("campaign_name", "") if state else ""

    entry = vault.save(username, char, campaign_name)
    return {"ok": True, "vault_entry": entry}


@app.get("/api/vault")
async def vault_list(morkrets_token: str | None = Cookie(None)):
    """Lista alla sparade karaktärer."""
    payload = _get_current_user(morkrets_token)
    entries = vault.list(payload["sub"])
    return {"characters": entries}


@app.post("/api/vault/use")
async def vault_use(req: VaultUseRequest, morkrets_token: str | None = Cookie(None)):
    """Hämta en karaktär ur valvet och sätt den som aktiv i kampanjen."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    entry = vault.get(username, req.char_id)
    if not entry:
        raise HTTPException(404, "Karaktären hittades inte i valvet")

    state["character"] = entry["character"]
    store.save(state)
    return {"ok": True, "character": entry["character"]}


@app.delete("/api/vault/{char_id}")
async def vault_delete(char_id: str, morkrets_token: str | None = Cookie(None)):
    """Radera en karaktär ur valvet."""
    payload = _get_current_user(morkrets_token)
    deleted = vault.delete(payload["sub"], char_id)
    if not deleted:
        raise HTTPException(404, "Karaktären hittades inte")
    return {"ok": True, "message": "Karaktären har raderats ur valvet"}


# ═══════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════


@app.get("/api/campaign/export")
async def export_campaign(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    buf = io.BytesIO()
    meta = state["meta"]

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # README.md
        readme = f"""# {meta['campaign_name']}

**Kampanj-ID:** {meta['campaign_id']}
**Skapad:** {meta['created']}
**Senast uppdaterad:** {meta['last_updated']}
**Turer:** {meta['turn_count']}
**Sessioner:** {meta.get('session_count', 1)}

## Karaktär
"""
        char = state.get("character", {})
        if char.get("name"):
            readme += f"- **Namn:** {char['name']}\n"
            readme += f"- **Ras/Klass:** {char.get('race', '?')} / {char.get('class', '?')}\n"
            readme += f"- **Nivå:** {char.get('level', 1)}\n"
        else:
            readme += "_Ingen karaktär skapad ännu._\n"

        readme += f"\n## Värld\n"
        world = state.get("world", {})
        readme += f"- **Plats:** {world.get('current_location', 'Okänd')}\n"
        readme += f"- **Tid:** {world.get('time', 'Okänd')}\n"

        zf.writestr("README.md", readme)

        # karaktar/
        if char:
            zf.writestr("karaktar/character.json", json.dumps(char, ensure_ascii=False, indent=2))

        # transkript/ — formatera JSONL till läsbar markdown
        tdir = store.get_transcripts_dir(state)
        if tdir.exists():
            for tfile in sorted(tdir.glob("session-*.jsonl")):
                md_lines = [f"# {tfile.stem}\n"]
                with open(tfile) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            role_label = "🧙 DM" if entry["role"] == "assistant" else "⚔️ Spelare"
                            md_lines.append(f"### {role_label}\n{entry['content']}\n")
                        except json.JSONDecodeError:
                            continue
                md_name = tfile.stem + ".md"
                zf.writestr(f"transkript/{md_name}", "\n".join(md_lines))

        # varlden/
        npcs = state.get("npcs", [])
        zf.writestr("varlden/npcs.json", json.dumps(npcs, ensure_ascii=False, indent=2))

        locations = state.get("locations", [])
        visited = state.get("world", {}).get("visited_locations", [])
        loc_data = {"locations": locations, "visited": visited}
        zf.writestr("varlden/platser.json", json.dumps(loc_data, ensure_ascii=False, indent=2))

        lore = state.get("lore", [])
        if isinstance(lore, list):
            lore_md = "\n\n".join(str(item) for item in lore) if lore else "_Ingen lore ännu._"
        else:
            lore_md = str(lore)
        zf.writestr("varlden/lore.md", f"# Lore\n\n{lore_md}\n")

        # summaries/
        sdir = store.get_summaries_dir(state)
        if sdir.exists():
            for sfile in sorted(sdir.glob("summary-*.json")):
                zf.writestr(f"summaries/{sfile.name}", sfile.read_text())

        # bilagor/ — bilder
        images = state.get("images", [])
        for img in images:
            if isinstance(img, dict) and img.get("path"):
                img_path = Path(img["path"])
                if img_path.exists():
                    zf.writestr(f"bilagor/{img_path.name}", img_path.read_bytes())

    buf.seek(0)
    filename = f"morkrets-rike-{meta['campaign_id']}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════

IMPORT_PROMPT = """Du är en dataextraktor för D&D-kampanjer. Analysera texten och extrahera strukturerad data.

Svara ENDAST med giltig JSON (ingen markdown):
{
  "characters": [{"name": "", "race": "", "class": "", "description": ""}],
  "npcs": [{"name": "", "role": "", "relation": "neutral", "notes": "", "alive": true}],
  "locations": [{"name": "", "description": ""}],
  "lore": ["string — viktiga världsdetaljer, historia, myter"],
  "items": [{"name": "", "type": "Annat", "description": "", "rarity": "normal"}]
}

Om en kategori saknas i texten, returnera tom array. Extrahera bara det som faktiskt finns."""


@app.post("/api/import")
async def import_file(
    file: UploadFile = File(...),
    model_id: str = "qwen3.8-max",
    morkrets_token: str | None = Cookie(None),
):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    # Validera filtyp
    fname = file.filename or ""
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("md", "pdf", "txt"):
        raise HTTPException(400, f"Filformat ej stöd: .{ext} (tillåtna: .md, .pdf, .txt)")

    content_bytes = await file.read()

    # Extrahera text
    if ext == "pdf":
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        except Exception as e:
            raise HTTPException(400, f"Kunde inte läsa PDF: {e}")
    else:
        text = content_bytes.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(400, "Filen är tom")

    # Trunkera om extremt lång
    if len(text) > 50000:
        text = text[:50000] + "\n\n[... trunkerad ...]"

    # Anropa LLM för extraktion
    messages = [
        {"role": "system", "content": IMPORT_PROMPT},
        {"role": "user", "content": f"Extrahera data från denna text:\n\n{text}"},
    ]

    try:
        raw = await _call_llm(model_id, messages, temperature=0.2, max_tokens=2048)
        extracted = _extract_json(raw)
    except ValueError as e:
        raise HTTPException(422, f"Kunde inte tolka LLM-svar: {e}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    # Merge in i state
    merged = {"characters": 0, "npcs": 0, "locations": 0, "lore": 0, "items": 0}

    # NPCs
    for npc in extracted.get("npcs", []):
        if isinstance(npc, dict) and npc.get("name"):
            # Undvik dubbletter
            existing_names = {n.get("name", "").lower() for n in state.get("npcs", [])}
            if npc["name"].lower() not in existing_names:
                state.setdefault("npcs", []).append(
                    {
                        "name": npc["name"],
                        "role": npc.get("role", "okänd"),
                        "relation": npc.get("relation", "neutral"),
                        "notes": npc.get("notes", ""),
                        "alive": npc.get("alive", True),
                    }
                )
                merged["npcs"] += 1

    # Locations
    for loc in extracted.get("locations", []):
        if isinstance(loc, dict) and loc.get("name"):
            existing_locs = {l.get("name", "").lower() for l in state.get("locations", [])}
            if loc["name"].lower() not in existing_locs:
                state.setdefault("locations", []).append(
                    {"name": loc["name"], "description": loc.get("description", "")}
                )
                merged["locations"] += 1

    # Lore
    for item in extracted.get("lore", []):
        if isinstance(item, str) and item.strip():
            state.setdefault("lore", []).append(item.strip())
            merged["lore"] += 1

    # Items → inventory
    for item in extracted.get("items", []):
        if isinstance(item, dict) and item.get("name"):
            state.setdefault("inventory", []).append(
                {
                    "id": f"import-{len(state.get('inventory', []))}",
                    "name": item["name"],
                    "type": item.get("type", "Annat"),
                    "qty": 1,
                    "weight": 0,
                    "equipped": False,
                    "rarity": item.get("rarity", "normal"),
                    "description": item.get("description", ""),
                }
            )
            merged["items"] += 1

    # Characters — spara som referens i lore om inte spelarkaraktär
    for char in extracted.get("characters", []):
        if isinstance(char, dict) and char.get("name"):
            state.setdefault("lore", []).append(
                f"Karaktär: {char['name']} ({char.get('race', '?')} {char.get('class', '?')}) — {char.get('description', '')}"
            )
            merged["characters"] += 1

    store.save(state)

    return {
        "ok": True,
        "filename": fname,
        "merged": merged,
        "total_chars_extracted": len(text),
    }


# ═══════════════════════════════════════
# WORLD BUILDING
# ═══════════════════════════════════════

WORLD_BUILD_PROMPT = """Du är en världsextraktor för D&D-kampanjer. Analysera spelarens beskrivning och extrahera strukturerad världdata.

Svara ENDAST med giltig JSON (ingen markdown):
{
  "locations": [{"name": "", "description": ""}],
  "npcs": [{"name": "", "role": "", "relation": "neutral", "notes": "", "alive": true}],
  "lore": ["string — viktiga världsdetaljer, historia, myter, stämning"]
}

Om en kategori saknas i beskrivningen, returnera tom array. Extrahera bara det som faktiskt finns."""


class WorldBuildRequest(BaseModel):
    prompt: str
    model_id: str = "qwen3.8-max"


@app.post("/api/world/build")
async def world_build(req: WorldBuildRequest, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    messages = [
        {"role": "system", "content": WORLD_BUILD_PROMPT},
        {"role": "user", "content": f"Bygg världen utifrån denna beskrivning:\n\n{req.prompt}"},
    ]

    try:
        raw = await _call_llm(req.model_id, messages, temperature=0.4, max_tokens=2048)
        extracted = _extract_json(raw)
    except ValueError as e:
        raise HTTPException(422, f"Kunde inte tolka LLM-svar: {e}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    merged = {"locations": 0, "npcs": 0, "lore": 0}

    # Locations
    for loc in extracted.get("locations", []):
        if isinstance(loc, dict) and loc.get("name"):
            existing_locs = {l.get("name", "").lower() for l in state.get("locations", [])}
            if loc["name"].lower() not in existing_locs:
                state.setdefault("locations", []).append(
                    {"name": loc["name"], "description": loc.get("description", "")}
                )
                merged["locations"] += 1

    # NPCs
    for npc in extracted.get("npcs", []):
        if isinstance(npc, dict) and npc.get("name"):
            existing_names = {n.get("name", "").lower() for n in state.get("npcs", [])}
            if npc["name"].lower() not in existing_names:
                state.setdefault("npcs", []).append({
                    "name": npc["name"],
                    "role": npc.get("role", "okänd"),
                    "relation": npc.get("relation", "neutral"),
                    "notes": npc.get("notes", ""),
                    "alive": npc.get("alive", True),
                })
                merged["npcs"] += 1

    # Lore
    for item in extracted.get("lore", []):
        if isinstance(item, str) and item.strip():
            state.setdefault("lore", []).append(item.strip())
            merged["lore"] += 1

    store.save(state)

    return {
        "ok": True,
        "merged": merged,
        "locations": extracted.get("locations", []),
        "npcs": extracted.get("npcs", []),
        "lore": extracted.get("lore", []),
    }


# ═══════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════


@app.get("/api/health")
async def health():
    return {"status": "ok", "game": "Mörkrets Rike"}


@app.get("/api/campaign/locations")
async def campaign_locations(morkrets_token: str | None = Cookie(None)):
    """Returnera alla kända platser med restid från nuvarande position."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")
    return get_locations_with_travel(state)


@app.get("/api/campaign/logbook")
async def campaign_logbook(morkrets_token: str | None = Cookie(None)):
    """Generera en äventyrsjournal (tidslinje) via LLM."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    # Samla transkript
    transcript = store.load_transcript(state, last_n=100)
    t_text = "\n".join(
        f"{e['role']}: {e['content']}" for e in transcript
    )

    # Samla sammanfattningar
    summaries = store.load_summaries(state, last_n=10)
    s_text = "\n".join(
        f"[Tur {s['turn']}]: {s['text']}" for s in summaries
    )

    if not t_text and not s_text:
        return {"title": "Mörkrets Rike", "days": [], "summary": "Äventyret har inte börjat ännu."}

    # Generera loggbok via LLM (snabb modell)
    campaign_name = state.get("meta", {}).get("campaign_name", "Mörkrets Rike")
    prompt = build_log_prompt(t_text, s_text, campaign_name)

    try:
        raw = await _call_llm(
            ATMOSPHERE_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        log_data = _extract_json(raw)
    except Exception:
        # Fallback: enkel struktur från state
        log_data = {
            "title": campaign_name,
            "days": [{
                "day": 1,
                "title": "Äventyret börjar",
                "mood": "Förväntansfull",
                "events": ["Kampanjen skapades"],
                "location": state.get("world", {}).get("current_location", "Okänd"),
                "npcs_met": [n.get("name", "?") for n in state.get("npcs", [])[:5]],
                "quests": [q.get("name", "?") for q in state.get("quests", []) if q.get("status") == "aktiv"],
            }],
            "summary": "Äventyret har just börjat. Mörkret väntar.",
        }

    return log_data


# ═══════════════════════════════════════
# STATIC FILES — serva frontend
# ═══════════════════════════════════════
# Monteras EFTER alla /api/ routes så att API:et har prioritet.

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
