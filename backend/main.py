"""
Mörkrets Rike — FastAPI Backend
=================================
LLM-driven D&D Dungeon Master. Alla endpoints under /api/.
"""

import asyncio
import copy
import io
import json
import logging
import os
import random
import re
import time
import uuid
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("morkrets")

# ═══════════════════════════════════════
# 🛠️ MASKINRUMMET — ringbuffer för live-debugloggar
# ═══════════════════════════════════════
# Fångar alla loggar från morkrets.* (main, rag, extraction, …) i en
# ringbuffer som frontend kan polla via /api/debug/logs. Påverkar inte
# den vanliga stdout-loggen — bara en extra kopia i minnet.
DEBUG_LOGS: deque = deque(maxlen=600)
_LOG_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

# Håller referenser till bakgrundsuppgifter så de inte garbage-collectas
# (asyncio.create_task returnerar en svag referens annars).
_BACKGROUND_TASKS: set = set()


class _RingBufferHandler(logging.Handler):
    """Kopierar varje loggpost till ringbuffern (för live-konsolen)."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            DEBUG_LOGS.append({
                "ts": record.created,
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "name": record.name.replace("morkrets", "mr").lstrip("."),
                "msg": record.getMessage(),
            })
        except Exception:
            pass  # Loggfångst får aldrig krascha spelet


_ring = _RingBufferHandler(level=logging.DEBUG)
logger.addHandler(_ring)
logger.setLevel(logging.DEBUG)

# StreamHandler → stdout (syns i docker logs)
_stream = logging.StreamHandler()
_stream.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
_stream.setLevel(logging.INFO)
logger.addHandler(_stream)

import httpx
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import create_token, load_users, verify_password, verify_token
from dice import roll as dice_roll
from models import (
    AWAKENING_ASK,
    AWAKENING_ASK_EN,
    AWAKENING_OPEN,
    AWAKENING_OPEN_EN,
    DM_COMBAT_PROMPT,
    DM_CORE_PROMPT,
    DM_NARRATIVE_PROMPT,
    DM_PROMPT_VERSION,
    ORACLE_PROMPT,
    get_api_key,
    get_model,
    list_models_for_frontend,
)
from atmosphere import (
    detect_environments,
    get_fallback_art,
    should_generate_art,
)
from locations import get_locations_with_travel, place_location
from logbook import build_log_prompt
from state_manager import CAMPAIGNS_DIR, CampaignStore, CharacterVault
import rag
from extraction import FactRegister, extract_facts, format_facts_block
from guardian import guardian_check_roll, guardian_extract_mechanics, apply_mechanics, format_guardian_summary

app = FastAPI(title="Mörkrets Rike", version="1.0.0")

# ═══════════════════════════════════════
# Language helpers
# ═══════════════════════════════════════

def _get_lang(state: dict) -> str:
    """Get campaign language from state (defaults to 'en')."""
    return state.get("meta", {}).get("language", "en")


def _err(msg_sv: str, msg_en: str, lang: str = "sv") -> str:
    """Return an error message in the campaign's language."""
    return msg_en if lang == "en" else msg_sv

# ═══════════════════════════════════════
# NPC-parsning + Äventyrsöppningar
# ═══════════════════════════════════════

NPC_PATTERN = re.compile(r'\[NPC:([^|]+)\|([^|]+)\|([^\]]+)\]')
KAST_PATTERN = re.compile(r'\[KAST:\s*([^\]|]+)(?:\|([^\]]+))?\]')

# Säkerhetsnät: DM skrev "rulla tärningen" i PROSA men glömde [KAST:]-taggen.
# Utan taggen spawnas ingen klickbar tärning → spelaren fastnar. Vi känner av
# uppmaningsfraser och auto-spawnar en 1d20 så spelet aldrig stannar.
PROSE_ROLL_PATTERN = re.compile(
    r'(rulla (en |din )?tärning|slå (en |din )?tärning|kasta (en |din )?tärning|'
    r'gör ett (tärnings)?slag|låt tärning\w* avgöra|tärning\w* avgör)',
    re.IGNORECASE,
)

# Säkerhetsnät: DM narrerar att spelaren FÅR/HITTAR/KÖPER ett föremål i prosa
# men glömde [FÖREMÅL:]-taggen. Utan taggen hamnar föremålet aldrig i inventory.
# VIKTIGT: Endast entydiga GÅVO-/FYND-verb. "ser", "tar", "får" är FÖR vanliga
# i svensk prosa och fångar meningsfragment ("ser lite besviken ut" → falskt föremål).
# PROSE_ITEM_PATTERN borttagen (v18) — LLM-extraktion i bakgrunden
# hanterar nu föremål som DM glömde tagga. Regex gav för många falska positiva.

# Nyckelord som indikerar en riskfylld handling → DM borde begära kast
ACTION_KEYWORDS = re.compile(
    r'\b(attackerar?|slår|hugger|skjuter|kastar|smyger|klättrar|hoppar|'
    r'springer|bryter|sparkar|slåss|fäktar|skär|sticker|hugg|skott|pil|'
    r'smyga|klättra|hoppa|springa|bryta|sparka|attack)\b',
    re.IGNORECASE,
)

NPC_COLORS = ['#8b5fd4', '#d4691e', '#7aa35e', '#5e9aa3', '#d43a4d', '#c9a227', '#a8b2c0', '#b06fd4']
NPC_ICONS = ['🧙', '⚔️', '🏹', '🛡️', '🎭', '👻', '🐺', '🦉', '💀', '🔮', '🗡️', '🌙']

OPENING_STYLES = [
    ('meeting', 'Äventyret börjar med att spelaren möter en intressant NPC. Ge dem ett namn, en personlighet och en anledning att vara där.'),
    ('alone', 'Spelaren är helt ensam. Beskriv omgivningen atmosfäriskt. Låt spelaren utforska och upptäcka saker i sin egen takt.'),
    ('in_media_res', 'Äventyret börjar mitt i en pågående händelse — en strid, en flykt, ett brinnande hus. Kasta spelaren rakt in.'),
    ('awakening', 'Spelaren vaknar på en okänd plats. De vet inte hur de hamnade där. Beskriv vad de ser, hör och känner.'),
    ('summoned', 'Spelaren har kallats till en plats av någon med ett uppdrag eller ett erbjudande. Vem kallade dem, och varför?'),
]

OPENING_STYLES_EN = [
    ('meeting', 'The adventure begins with the player meeting an interesting NPC. Give them a name, a personality, and a reason to be there.'),
    ('alone', 'The player is completely alone. Describe the surroundings atmospherically. Let the player explore and discover things at their own pace.'),
    ('in_media_res', 'The adventure begins in the middle of an ongoing event — a battle, an escape, a burning house. Throw the player straight in.'),
    ('awakening', 'The player wakes up in an unknown place. They do not know how they got there. Describe what they see, hear, and feel.'),
    ('summoned', 'The player has been summoned to a place by someone with a quest or an offer. Who summoned them, and why?'),
]


def _parse_npcs(text: str) -> tuple[str, list[dict]]:
    """Extrahera [NPC:namn|roll|relation]-taggar ur DM-svar."""
    npcs = []
    for m in NPC_PATTERN.finditer(text):
        name, role, relation = m.group(1).strip(), m.group(2).strip(), m.group(3).strip().lower()
        if relation not in ('allierad', 'neutral', 'fiende', 'okänd'):
            relation = 'okänd'
        # Hash-baserad färg/ikon: samma NPC får alltid samma färg oavsett
        # när den dyker upp (istället för att bero på parse-ordning).
        h = int.from_bytes(name.encode('utf-8'), 'big')
        npcs.append({
            'name': name, 'role': role, 'relation': relation,
            'color': NPC_COLORS[h % len(NPC_COLORS)],
            'icon': NPC_ICONS[h % len(NPC_ICONS)],
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
    'SILVER':          re.compile(r'\[SILVER:(-?\d+)\]'),
    'KOPPAR':          re.compile(r'\[KOPPAR:(-?\d+)\]'),
    'PLATINA':         re.compile(r'\[PLATINA:(-?\d+)\]'),
    'FÖREMÅL':         re.compile(r'\[FÖREMÅL:([^|\]]+)(?:\|([^|\]]+))?(?:\|([^\]]+))?\]'),
    'QUEST':           re.compile(r'\[QUEST:([^|\]]+)(?:\|([^|\]]+))?(?:\|([^\]]+))?\]'),
    'QUEST_SLUTFÖRD':  re.compile(r'\[QUEST_SLUTFÖRD:([^\]]+)\]'),
    'QUEST_MISSLYCKAD': re.compile(r'\[QUEST_MISSLYCKAD:([^\]]+)\]'),
    'KONSEKVENS':      re.compile(r'\[KONSEKVENS:([^\]]+)\]'),
    'NPC_DÖD':         re.compile(r'\[NPC_DÖD:([^\]]+)\]'),
    'PLATS':           re.compile(r'\[PLATS:([^\]]+)\]'),
    'TID':             re.compile(r'\[TID:([^\]]+)\]'),
    'FÖREMÅL_BORT':    re.compile(r'\[FÖREMÅL_BORT:([^\]]+)\]'),
    'NPC_RELATION':    re.compile(r'\[NPC_RELATION:([^|\]]+)\|([^\]]+)\]'),
    'NY_DAG':          re.compile(r'\[NY_DAG:([^\]]+)\]'),
}

# ── D&D 5e Valutasystem ──
# Konvertering: 1 pp = 10 gp = 100 sp = 1000 cp (ep hoppas över för enkelhet)
# Vikt: 50 mynt = 1 lb oavsett valör
COIN_TO_CP = {'pp': 1000, 'gp': 100, 'sp': 10, 'cp': 1}
COIN_NAMES = {'pp': 'platina', 'gp': 'guld', 'sp': 'silver', 'cp': 'koppar'}


def normalize_currency(currency: dict) -> dict:
    """Konvertera överflöde uppåt: cp → sp → gp → pp.
    Exempel: {cp: 25, sp: 0, gp: 0, pp: 0} → {cp: 5, sp: 2, gp: 0, pp: 0}
    """
    total_cp = sum(currency.get(d, 0) * COIN_TO_CP[d] for d in COIN_TO_CP)
    total_cp = max(0, total_cp)
    result = {}
    for denom in ('pp', 'gp', 'sp', 'cp'):
        value = COIN_TO_CP[denom]
        result[denom] = total_cp // value
        total_cp %= value
    return result


def currency_to_cp(currency: dict) -> int:
    """Totalt värde i kopparmynt."""
    return sum(currency.get(d, 0) * COIN_TO_CP[d] for d in COIN_TO_CP)


def currency_weight(currency: dict) -> float:
    """Vikt i lb — 50 mynt = 1 lb oavsett valör."""
    total_coins = sum(currency.get(d, 0) for d in COIN_TO_CP)
    return round(total_coins / 50, 2)


def currency_display(currency: dict) -> str:
    """Mänskligt läsbar sträng: '2 pp, 15 gp, 3 sp, 7 cp' (skippar nollor)."""
    parts = []
    for d in ('pp', 'gp', 'sp', 'cp'):
        v = currency.get(d, 0)
        if v > 0:
            parts.append(f"{v} {d}")
    return ', '.join(parts) if parts else '0 gp'


def apply_currency(state: dict, denom: str, amount: int) -> tuple[bool, str]:
    """Lägg till eller dra av mynt. Normaliserar efteråt.
    Returnerar (success, message). Vid negativt saldo: vägrar.
    """
    currency = state.setdefault('currency', {'pp': 0, 'gp': 0, 'sp': 0, 'cp': 0})
    # Säkerställ att alla valörer finns
    for d in COIN_TO_CP:
        currency.setdefault(d, 0)

    if amount >= 0:
        currency[denom] = currency.get(denom, 0) + amount
        state['currency'] = normalize_currency(currency)
        return True, f"+{amount} {COIN_NAMES[denom]}"
    else:
        # Kontrollera att saldot räcker (i cp)
        needed_cp = abs(amount) * COIN_TO_CP[denom]
        available_cp = currency_to_cp(currency)
        if needed_cp > available_cp:
            logger.warning(
                f"Valuta: försök spendera {abs(amount)} {COIN_NAMES[denom]} "
                f"men saldot är bara {currency_display(currency)}"
            )
            return False, f"Otillräckligt saldo: behövde {abs(amount)} {COIN_NAMES[denom]}, hade {currency_display(currency)}"
        # Dra av
        currency[denom] = currency.get(denom, 0) + amount  # amount är negativt
        # Om valören blev negativ, växla ner från högre valörer
        state['currency'] = normalize_currency(currency)
        return True, f"-{abs(amount)} {COIN_NAMES[denom]}"


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

    # VALUTA — guld, silver, koppar, platina
    _CURRENCY_TAGS = [
        ('GULD', 'gp'), ('SILVER', 'sp'), ('KOPPAR', 'cp'), ('PLATINA', 'pp'),
    ]
    for tag_name, denom in _CURRENCY_TAGS:
        for m in _MECH_PATTERNS[tag_name].finditer(text):
            amount = int(m.group(1))
            ok, msg = apply_currency(state, denom, amount)
            if ok:
                effects.append({'type': 'guld', 'value': amount, 'denom': denom, 'msg': msg})
            else:
                effects.append({'type': 'guld_fail', 'value': amount, 'denom': denom, 'msg': msg})

    # FÖREMÅL — lägg till i inventariet (med deduplicering)
    for m in _MECH_PATTERNS['FÖREMÅL'].finditer(text):
        name = m.group(1).strip()
        item_type = (m.group(2) or 'Annat').strip()
        rarity = (m.group(3) or 'normal').strip()
        inv = state.setdefault('inventory', [])
        # Deduplicering: samma namn (skiftlägesokänsligt) → qty++
        existing = next((it for it in inv if it['name'].lower() == name.lower()), None)
        if existing:
            existing['qty'] = existing.get('qty', 1) + 1
            logger.info("📦 Dedup: '%s' → qty=%d", name, existing['qty'])
        else:
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

    # PLATS — uppdatera nuvarande plats + lägg till i locations[]
    for m in _MECH_PATTERNS['PLATS'].finditer(text):
        name = m.group(1).strip()
        world = state.setdefault('world', {})
        old_loc = world.get('current_location', '')
        world['current_location'] = name
        # Ruttspårning: logga förflyttningar
        if old_loc and old_loc != name:
            travel_log = world.setdefault('travel_log', [])
            travel_log.append({'from': old_loc, 'to': name, 'day': world.get('day', 1)})
        visited = world.setdefault('visited_locations', [])
        if name not in visited:
            visited.append(name)
        # Lägg till i locations-arrayen (så kartan kan visa den)
        locs = state.setdefault('locations', [])
        if not any(l.get('name', '').lower() == name.lower() for l in locs):
            placed = place_location(name, state.get('meta', {}).get('campaign_id', ''))
            locs.append({
                'name': name, 'description': '', 'terrain': placed['terrain'],
                'x': placed['x'], 'y': placed['y'],
            })
        effects.append({'type': 'plats', 'value': name})

    # TID — uppdatera tid/väder
    for m in _MECH_PATTERNS['TID'].finditer(text):
        desc = m.group(1).strip()
        world = state.setdefault('world', {})
        world['time'] = desc
        effects.append({'type': 'tid', 'value': desc})

    # FÖREMÅL_BORT — ta bort föremål ur inventariet
    for m in _MECH_PATTERNS['FÖREMÅL_BORT'].finditer(text):
        name = m.group(1).strip().lower()
        inv = state.get('inventory', [])
        state['inventory'] = [it for it in inv if it.get('name', '').lower() != name]
        effects.append({'type': 'föremål_bort', 'value': m.group(1).strip()})

    # NPC_RELATION — uppdatera en NPCs relation
    for m in _MECH_PATTERNS['NPC_RELATION'].finditer(text):
        npc_name = m.group(1).strip().lower()
        new_rel = m.group(2).strip()
        for npc in state.get('npcs', []):
            if npc.get('name', '').lower() == npc_name:
                npc['relation'] = new_rel
                break
        effects.append({'type': 'npc_relation', 'value': f"{m.group(1).strip()} → {new_rel}"})

    # NY_DAG — ny dag i äventyret
    for m in _MECH_PATTERNS['NY_DAG'].finditer(text):
        desc = m.group(1).strip()
        world = state.setdefault('world', {})
        world['day'] = world.get('day', 1) + 1
        world['day_description'] = desc
        world.setdefault('day_log', []).append({'day': world['day'], 'description': desc})
        # Markera att en dag-entry ska genereras i bakgrunden
        world['_pending_day_entry'] = True
        effects.append({'type': 'ny_dag', 'value': f"Dag {world['day']}: {desc}"})

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
ATMOSPHERE_MODEL = os.getenv("ATMOSPHERE_MODEL", "mimo-v2.5")
ATMOSPHERE_ENABLED = os.getenv("ATMOSPHERE_ENABLED", "0") == "1"
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "qwen3.6-flash")
# Guardian: smartare modell för kontextmedveten mekanisk extraktion
# (NPC-avslöjanden, implicita relationsändringar, karaktärsuppdateringar)
GUARDIAN_MODEL = os.getenv("GUARDIAN_MODEL", "qwen3.8-max")


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


class CampaignCreateRequest(BaseModel):
    name: str = ""
    language: str = "en"


class CampaignActivateRequest(BaseModel):
    campaign_id: str


class SaveRequest(BaseModel):
    description: str = ""


class PinRequest(BaseModel):
    fact: str


class LoreRequest(BaseModel):
    text: str


class ChapterRequest(BaseModel):
    title: str


class LoadRequest(BaseModel):
    save_id: str


# ═══════════════════════════════════════
# DM-svarsvalidering (Pydantic) + regelinjicering
# ═══════════════════════════════════════


class DMResponse(BaseModel):
    """Validerad struktur för ett DM-svar efter taggparsning."""
    narration: str
    effects: list = []
    roll_requests: list = []
    valid: bool = True


def validate_dm_response(
    narration: str, effects: list, roll_requests: list, state: dict
) -> tuple[DMResponse, list[str]]:
    """
    Validera mekaniken i ett DM-svar mot kampanjtillståndet.
    Returnerar (DMResponse, lista_med_fel). Tom fellista = giltigt.

    Kontroller:
      - HP-förändringar (skada/hela) får inte överskrida max-HP
      - XP måste vara positivt
      - Föremålsnamn får inte vara tomma
      - Questnamn får inte vara tomma
    """
    errors: list[str] = []
    char = state.get("character", {})
    hp = char.get("hp", {})
    hp_max = hp.get("max", 10)
    hp_current = hp.get("current", hp_max)

    for fx in effects:
        ftype = fx.get("type", "")
        value = fx.get("value")
        if ftype == "skada":
            try:
                amt = int(value)
            except (TypeError, ValueError):
                errors.append(f"Ogiltig skada: {value!r}")
                continue
            if amt > hp_max:
                errors.append(f"Skada {amt} överstiger max-HP {hp_max}")
        elif ftype == "hela":
            try:
                amt = int(value)
            except (TypeError, ValueError):
                errors.append(f"Ogiltig helande: {value!r}")
                continue
            if hp_current + amt > hp_max and amt > hp_max:
                errors.append(f"Helande {amt} överstiger max-HP {hp_max}")
        elif ftype == "xp":
            try:
                amt = int(value)
            except (TypeError, ValueError):
                errors.append(f"Ogiltig XP: {value!r}")
                continue
            if amt <= 0:
                errors.append(f"XP måste vara positivt, fick {amt}")
        elif ftype == "föremål":
            if not value or not str(value).strip():
                errors.append("Föremålsnamn får inte vara tomt")
        elif ftype == "quest":
            if not value or not str(value).strip():
                errors.append("Questnamn får inte vara tomt")

    dm_resp = DMResponse(
        narration=narration,
        effects=effects,
        roll_requests=roll_requests,
        valid=len(errors) == 0,
    )
    return dm_resp, errors


def _strip_mechanical_tags(text: str) -> str:
    """Ta bort alla mekaniska taggar ur text (används vid förkastande av trasig mekanik)."""
    clean = text
    for pattern in _MECH_PATTERNS.values():
        clean = pattern.sub("", clean)
    return re.sub(r"\n{3,}", "\n\n", clean).strip()


# ── Per-turs regelinjicering (D&D 5e) ──

RULES_DB: dict[str, str] = {
    "attack": "ATTACK: Slå 1d20 + attackmodifierare (STY/SMI) mot målets AC. Träff → skada. Naturlig 20 = kritisk träff (dubbla skadetärningar), naturlig 1 = automatisk miss.",
    "sneak": "SMYGNING: Slå 1d20 + Smidighet (Smygning) mot fiendernas passiva Perception (10 + Perception-mod). Lyckas = du är osedd och kan få överraskning/fördel.",
    "climb": "KLÄTTRING: Slå 1d20 + Styrka (Atletik) mot en DC satt av DM (typiskt DC 10–15 för klättring). Misslyckande = fall eller ingen framgång.",
    "jump": "HOPP: Styrka (Atletik)-slag för långt/högt hopp utöver normal räckvidd. Långt hopp = 3 + STY-mod i fot, högt = 3 + STY-mod halverat i fot.",
    "persuade": "ÖVERTALNING: Slå 1d20 + Karisma (Övertalning) mot målets Insight eller en DC. Lyckas = NPC:n går med på rimlig begäran.",
    "deceive": "VILSELEDANDE: Slå 1d20 + Karisma (Vilseledande) mot målets Insight. Lyckas = målet tror på lögnen.",
    "search": "SÖKANDE/UNDERSÖKA: Slå 1d20 + Intelligens (Undersökning) mot en DC. Hittar dolda detaljer, ledtrådar och mekanismer.",
    "trap": "FÄLLA: Oftast ett Smidighets-räddningsslag (1d20 + SMI-mod) mot fällans DC. Lyckas = halv eller ingen skada.",
    "poison": "GIFT: Vanligtvis ett Kondition-räddningsslag (1d20 + KON-mod) mot giftets DC. Misslyckande = skada eller tillstånd (förgiftad).",
    "spell": "BESVÄRJELSE: Magiska attacker slår 1d20 + besvärjelsemodifierare mot AC, ELLER så gör målet ett räddningsslag mot din Spell Save DC (8 + prof + besvärjelse-mod).",
    "rest": "VILA: Kort vila (1h) → återfå HP via Hit Dice. Lång vila (8h) → full HP + återfå Hit Dice (upp till halva totalen).",
    "death_save": "DÖDSRÄDDNING: Vid 0 HP, slå 1d20 varje tur. 10+ = framgång, <10 = misslyckande. 3 framgångar = stabil, 3 misslyckanden = död. Naturlig 1 = 2 misslyckanden, naturlig 20 = vakna med 1 HP.",
    "surprise": "ÖVERRASKNING: Om en sida inte märker den andra får de en överraskningsrunda — de överraskade kan inte röra sig eller agera första rundan.",
    "cover": "SKYDD: Halvt skydd = +2 AC & SMI-räddningar. Tre fjärdedels skydd = +5. Fullt skydd = kan inte träffas direkt.",
    "condition": "TILLSTÅND: Vanliga: Liggande (prone) — nackdel på attacker, attacker inom 5 fot har fördel. Bedövad (stunned) — kan inte agera, attacker har fördel mot dig. Förgiftad — nackdel på attacker & förmågeslag.",
}


def inject_rules(player_input: str) -> str:
    """
    Extrahera nyckelord ur spelarens meddelande, matcha mot RULES_DB
    och returnera de 3 mest relevanta reglerna som formaterad sträng.
    """
    if not player_input:
        return ""

    text = player_input.lower()

    # Nyckelordsgrupper — svenska/engelska termer som mappar till RULES_DB-nycklar
    keyword_map = {
        "attack": ["attack", "attackerar", "slår", "hugger", "skjuter", "strid", "svärd", "vapen", "pil", "skott"],
        "sneak": ["smyg", "smyger", "smyga", "ljudlös", "gömma", "gömmer", "osynlig", "lönn"],
        "climb": ["klättr", "klättrar", "klättra", "vägg", "berg", "upp för"],
        "jump": ["hopp", "hoppar", "hoppa", "hoppa över", "klyfta", "avgrund"],
        "persuade": ["övertal", "övertyga", "förhandla", "charma", "charm", "diplomati"],
        "deceive": ["lura", "ljug", "lögn", "bedra", "vilseled", "fejka", "bluff"],
        "search": ["sök", "söker", "undersök", "leta", "letar", "granska", "genomsök", "rotar"],
        "trap": ["fälla", "fällor", "snara", "mekanism", "utlösare"],
        "poison": ["gift", "giftig", "förgift", "motgift", "dryck"],
        "spell": ["besvärjelse", "magi", "troll", "trollformel", "kasta en besvärjelse", "eldklot", "mana"],
        "rest": ["vila", "vilar", "sova", "sömn", "läger", "rast"],
        "death_save": ["döende", "dör", "medvetslös", "blöder ut", "0 hp", "nära döden"],
        "surprise": ["överrask", "överfall", "bakhåll", "smygattack", "överrumpla"],
        "cover": ["skydd", "täckning", "gömmer sig bakom", "mur", "sköld", "barrikad"],
        "condition": ["knuffa", "vält", "bedöva", "förlama", "skräck", "förblinda", "liggande"],
    }

    scores: dict[str, int] = {}
    for rule_key, words in keyword_map.items():
        for w in words:
            if w in text:
                scores[rule_key] = scores.get(rule_key, 0) + 1

    if not scores:
        return ""

    # Sortera efter poäng (fallande), ta topp 3
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:3]
    lines = [f"- {RULES_DB[key]}" for key, _ in top if key in RULES_DB]
    if not lines:
        return ""
    return "\n".join(lines)


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
    timeout: float = 180,
    reasoning_effort: str | None = None,
    thinking_cap: int = 16000,
) -> str:
    """Anropa vald modell via OpenAI-kompatibelt /chat/completions.
    Reasoning-modeller (deepseek-v4-flash) behöver högre max_tokens
    eftersom de tänker innan de svarar. `timeout` sänks för icke-kritiska
    anrop (t.ex. ASCII-art) så de aldrig blockerar spelupplevelsen."""
    config = get_model(model_id)
    api_key = get_api_key(config)

    # Reasoning-modeller behöver mer utrymme (thinking + content)
    if config.api_model in ("deepseek-v4-flash", "mimo-v2.5", "mimo-v2.5-pro", "step-3.7-flash"):
        max_tokens = max(max_tokens, 2048)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": config.api_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # StepFun 3.7 Flash: debiterar per prompt, inte per token → high överallt.
    # High reasoning kräver stor tokenbudget (tanke + svar).
    if config.api_model == "step-3.7-flash":
        body["reasoning_effort"] = reasoning_effort or "high"
        body["max_tokens"] = max(body.get("max_tokens", 1024), 8000)

    # Qwen3-modeller: thinking mode PÅ som standard. Ge generöst med
    # utrymme så modellen kan tänka fritt OCH leverera svaret.
    if config.provider == "dashscope" and config.api_model.startswith("qwen3"):
        if reasoning_effort == "off":
            body["enable_thinking"] = False
        else:
            # Thinking på → rejäl budget (tanke + svar)
            body["max_tokens"] = max(body.get("max_tokens", 1024), thinking_cap)

    url = f"{config.base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise HTTPException(
                502, f"LLM-fel ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        content = data["choices"][0]["message"].get("content", "")
        if not content:
            # Reasoning-modeller (StepFun, DeepSeek) kan lägga svaret i
            # reasoning/reasoning_content och lämna content tomt.
            msg = data["choices"][0]["message"]
            reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
            if reasoning:
                logger.info(
                    "🧠 %s: tomt content → använder reasoning (%d tecken)",
                    config.api_model, len(reasoning),
                )
                return reasoning
            logger.warning("🧠 %s returnerade helt tomt svar", config.api_model)
            return ""
        return content


async def _call_llm_with_reasoning(
    model_id: str,
    messages: list[dict],
    temperature: float = 0.8,
    max_tokens: int = 1024,
    timeout: float = 180,
) -> tuple[str, str, dict]:
    """Som _call_llm men fångar även reasoning-modellens inre monolog
    (reasoning_content). Returnerar (content, reasoning, usage). Används för
    huvud-DM-anropet så spelaren kan se hur DM:n resonerar."""
    config = get_model(model_id)
    api_key = get_api_key(config)

    # Reasoning-modeller behöver mer utrymme (thinking + content)
    if config.api_model in ("deepseek-v4-flash", "mimo-v2.5", "mimo-v2.5-pro", "step-3.7-flash"):
        max_tokens = max(max_tokens, 4096)

    # Qwen3: thinking mode PÅ som standard — ge generös budget
    if config.provider == "dashscope" and config.api_model.startswith("qwen3"):
        max_tokens = max(max_tokens, 16000)

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

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise HTTPException(
                502, f"LLM-fel ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content", "")
        reasoning = (message.get("reasoning_content") or "").strip()
        if not content:
            raise RuntimeError(
                "Modellen returnerade tomt svar (reasoning-modell?)"
            )
        return content, reasoning, data.get("usage", {})


def _extract_json(text: str) -> dict:
    """Extrahera JSON från LLM-svar (kan vara inbäddat i markdown eller reasoning-taggar)."""
    if not text or not text.strip():
        raise ValueError("Tomt svar från modellen")

    # Ta bort reasoning-taggar (deepseek-v4-flash: <think>, Qwen3: )
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = re.sub(r"", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

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
    # Hitta första { ... } (balanserat)
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    # Fallback: första { till sista }
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
# REGELORAKLET — Qwen-driven (ersätter hårdkodade svar)
# ═══════════════════════════════════════


class OracleRequest(BaseModel):
    question: str
    model_id: str = "step-3.7-flash"


@app.post("/api/oracle")
async def oracle(req: OracleRequest, morkrets_token: str | None = Cookie(None)):
    """Ställ en regelfråga till Regeloraklet (LLM)."""
    _get_current_user(morkrets_token)
    if not req.question.strip():
        raise HTTPException(400, "Ställ en fråga först")
    try:
        answer = await _call_llm(
            req.model_id,
            [
                {"role": "system", "content": ORACLE_PROMPT},
                {"role": "user", "content": req.question},
            ],
            temperature=0.4,
            max_tokens=300,
        )
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        raise HTTPException(502, f"Oraklet tiger: {e}")
    return {"answer": answer.strip()}


# ═══════════════════════════════════════
# TTS — StepAudio 2.5 (text-till-ljud)
# ═══════════════════════════════════════

TTS_VOICES = [
    {"id": "cixingnansheng", "name": "Berättaren (mörk)", "desc": "Dramatic male narrator"},
    {"id": "cixingnvsheng", "name": "Sagorösten (ljus)", "desc": "Warm female narrator"},
    {"id": "zhixingnansheng", "name": "Krigaren (kraftfull)", "desc": "Powerful male voice"},
    {"id": "zhixingnvsheng", "name": "Häxan (mystisk)", "desc": "Mysterious female voice"},
]


class TTSRequest(BaseModel):
    text: str
    voice: str = "cixingnansheng"


def _truncate_tts(text: str, limit: int = 1000) -> str:
    """Trunkera till max `limit` tecken vid sista meningsgränsen."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Hitta sista meningsavslut (. ! ? …) följt av mellanslag eller slut
    for m in reversed(list(re.finditer(r'[.!?…]\s', cut))):
        return cut[: m.end()].strip()
    # Ingen meningsgräns — hårklipp vid sista mellanslag
    sp = cut.rfind(' ')
    return cut[:sp].strip() if sp > 0 else cut.strip()


@app.get("/api/tts/voices")
async def tts_voices(morkrets_token: str | None = Cookie(None)):
    """Tillgängliga TTS-röster."""
    _get_current_user(morkrets_token)
    return {"voices": TTS_VOICES}


@app.post("/api/tts")
async def tts(req: TTSRequest, morkrets_token: str | None = Cookie(None)):
    """Generera tal från text via StepAudio 2.5."""
    _get_current_user(morkrets_token)
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Ingen text att läsa upp")
    text = _truncate_tts(text)

    api_key = os.getenv("STEPFUN_API_KEY")
    if not api_key:
        raise HTTPException(500, "TTS-tjänsten är inte konfigurerad")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.stepfun.ai/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "stepaudio-2.5-tts",
                    "voice": req.voice,
                    "input": text,
                    "instruction": "Narrate in a dramatic, immersive fantasy storytelling voice. Dark and atmospheric.",
                },
            )
        if resp.status_code != 200:
            logger.error("TTS API error %s: %s", resp.status_code, resp.text[:300])
            raise HTTPException(502, "Kunde inte generera ljud — TTS-tjänsten svarade inte")
        return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("TTS error: %s", e)
        raise HTTPException(502, "Kunde inte generera ljud — oväntat fel")


# ═══════════════════════════════════════
# CAMPAIGN CRUD
# ═══════════════════════════════════════


@app.post("/api/campaign")
async def create_campaign(body: CampaignCreateRequest | None = None, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    name = (body.name if body else "") or "Ett namnlöst äventyr"
    language = (body.language if body else "en") or "en"

    state = store.create(username, name=name, language=language)
    # Slumpa en äventyrsöppning (språkmedveten)
    styles = OPENING_STYLES_EN if language == "en" else OPENING_STYLES
    style_key, style_desc = random.choice(styles)
    state["meta"]["opening_style"] = style_desc
    state["meta"]["opening_key"] = style_key
    state["meta"]["awakening"] = True  # DM vaknar: frågor först, sen öppnas scenen
    store.save(state)
    return {"ok": True, "campaign_id": state["meta"]["campaign_id"], "opening": style_key}


@app.get("/api/campaign")
async def get_campaign(morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")
    return state


@app.get("/api/campaign/transcript")
async def get_transcript(morkrets_token: str | None = Cookie(None)):
    """Returnera kampanjens transkript (senaste 100 meddelandena).
    Inkluderar även senaste tur's effekter + kastbegäran så att
    transkript-fallbacken kan återställa föremål/kast som tappades
    när HTTP-anslutningen timeout:ade."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")
    entries = store.load_transcript(state, last_n=100)
    meta = state.get("meta", {})
    return {
        "messages": entries,
        "last_effects": meta.get("last_effects", []),
        "last_roll_requests": meta.get("last_roll_requests", []),
    }


@app.get("/api/campaigns")
async def list_campaigns(morkrets_token: str | None = Cookie(None)):
    """Lista alla kampanjer för användaren."""
    payload = _get_current_user(morkrets_token)
    campaigns = store.list_campaigns(payload["sub"])
    return {"campaigns": campaigns}


@app.delete("/api/campaign")
async def delete_campaign(
    morkrets_token: str | None = Cookie(None),
    campaign_id: str | None = None,
):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    # Accept campaign_id from query param or body
    cid = campaign_id
    if not cid:
        raise HTTPException(400, "campaign_id krävs för att radera en specifik kampanj")
    deleted = store.delete(username, cid)
    if not deleted:
        raise HTTPException(404, "Ingen kampanj att radera")
    # Fas 3: Rensa Qdrant-vektorer så inget långtidsminne läcker kvar
    try:
        await rag.purge_user(username)
    except Exception as e:
        logger.debug("Qdrant-rensning vid kampanjradering: %s", e)
    return {"ok": True, "message": "Kampanjen har avslutats och raderats"}


@app.post("/api/campaign/activate")
async def activate_campaign(body: CampaignActivateRequest, morkrets_token: str | None = Cookie(None)):
    """Sätt en specifik kampanj som aktiv."""
    payload = _get_current_user(morkrets_token)
    state = store.set_active(payload["sub"], body.campaign_id)
    if not state:
        raise HTTPException(404, "Kampanjen hittades inte")
    return {"ok": True, "campaign_id": body.campaign_id}


# ═══════════════════════════════════════
# SAVE / LOAD / PIN / LORE / CHAPTER
# ═══════════════════════════════════════


@app.post("/api/campaign/save")
async def save_checkpoint(body: SaveRequest, morkrets_token: str | None = Cookie(None)):
    """Spara en snapshot av nuvarande kampanjtillstånd."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    user = state["meta"]["user"]
    cid = state["meta"]["campaign_id"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    save_id = f"save-{ts}"

    saves_dir = store._saves_dir(user, cid)
    saves_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "save_id": save_id,
        "description": body.description or f"Sparat vid tur {state['meta'].get('turn_count', 0)}",
        "created": datetime.now(timezone.utc).isoformat(),
        "turn_count": state["meta"].get("turn_count", 0),
        "character": state.get("character", {}),
        "inventory": state.get("inventory", []),
        "currency": state.get("currency", {}),
        "npcs": state.get("npcs", []),
        "quests": state.get("quests", []),
        "world": state.get("world", {}),
        "lore": state.get("lore", []),
        "pinned_facts": state.get("pinned_facts", []),
    }
    save_path = saves_dir / f"{save_id}.json"
    with open(save_path, "w") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return {"ok": True, "save_id": save_id, "description": snapshot["description"], "turn_count": snapshot["turn_count"]}


@app.get("/api/campaign/saves")
async def list_saves(morkrets_token: str | None = Cookie(None)):
    """Lista alla sparade checkpoints för kampanjen."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    saves_dir = store._saves_dir(state["meta"]["user"], state["meta"]["campaign_id"])
    saves = []
    if saves_dir.exists():
        for sf in sorted(saves_dir.glob("save-*.json"), reverse=True):
            try:
                with open(sf) as f:
                    data = json.load(f)
                saves.append({
                    "save_id": data.get("save_id", sf.stem),
                    "description": data.get("description", ""),
                    "created": data.get("created", ""),
                    "turn_count": data.get("turn_count", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return {"saves": saves}


@app.post("/api/campaign/load")
async def load_save(body: LoadRequest, morkrets_token: str | None = Cookie(None)):
    """Återställ kampanjtillstånd från en sparad checkpoint."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    saves_dir = store._saves_dir(state["meta"]["user"], state["meta"]["campaign_id"])
    save_path = saves_dir / f"{body.save_id}.json"
    if not save_path.exists():
        raise HTTPException(404, f"Sparfil '{body.save_id}' hittades inte")

    with open(save_path) as f:
        snapshot = json.load(f)

    # Återställ fält från snapshot
    for key in ("character", "inventory", "currency", "npcs", "quests", "world", "lore", "pinned_facts"):
        if key in snapshot:
            state[key] = snapshot[key]
    if "turn_count" in snapshot:
        state["meta"]["turn_count"] = snapshot["turn_count"]

    store.save(state)
    return {"ok": True, "restored_from": body.save_id, "state": state}


@app.post("/api/campaign/pin")
async def pin_fact(body: PinRequest, morkrets_token: str | None = Cookie(None)):
    """Fäst en fakta som permanent sanning."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    facts = state.setdefault("pinned_facts", [])
    fact = body.fact.strip()
    if fact and fact not in facts:
        facts.append(fact)
    store.save(state)
    return {"ok": True, "pinned_facts": facts}


@app.delete("/api/campaign/pin")
async def unpin_fact(body: PinRequest, morkrets_token: str | None = Cookie(None)):
    """Ta bort en fäst fakta."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    facts = state.setdefault("pinned_facts", [])
    fact = body.fact.strip()
    if fact in facts:
        facts.remove(fact)
    store.save(state)
    return {"ok": True, "pinned_facts": facts}


@app.post("/api/campaign/lore")
async def add_lore(body: LoreRequest, morkrets_token: str | None = Cookie(None)):
    """Lägg till en lore-post till kampanjen."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    lore = state.setdefault("lore", [])
    text = body.text.strip()
    if text:
        lore.append(text)
        # Fas 3: Indexera lore i Qdrant för semantisk sökning
        try:
            campaign_id = state["meta"].get("campaign_id", "")
            await rag.index_lore(f"Lore #{len(lore)}", text, payload["sub"], campaign_id)
        except Exception as e:
            logger.debug("Lore-indexering hoppade över: %s", e)
    store.save(state)
    return {"ok": True, "lore_count": len(lore)}


@app.get("/api/facts")
async def get_facts(category: str | None = None, morkrets_token: str | None = Cookie(None)):
    """Hämta faktaregistret (alla eller filtrerade per kategori)."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    campaign_id = state["meta"]["campaign_id"] if state else ""
    try:
        register = FactRegister(payload["sub"], campaign_id)
        if category:
            facts = register.get_facts_by_category(category)
        else:
            facts = [f for f in register._facts if not f.superseded_by]
        return {
            "facts": [f.model_dump() for f in facts],
            "stats": register.stats(),
        }
    except Exception:
        return {"facts": [], "stats": {}}


@app.post("/api/campaign/chapter")
async def trigger_chapter(body: ChapterRequest, morkrets_token: str | None = Cookie(None)):
    """Manuellt utlös en kapitalsammanfattning via LLM."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    # Bygg kontext från transkript + state
    transcript = store.load_transcript(state, last_n=30)
    t_text = "\n".join(f"{e['role']}: {e['content']}" for e in transcript[-20:])
    char_name = state.get("character", {}).get("name", "Äventyraren")
    location = state.get("world", {}).get("current_location", "Okänd plats")
    npcs = ", ".join(n.get("name", "?") for n in state.get("npcs", [])[:8])
    quests = ", ".join(q.get("name", "?") for q in state.get("quests", []) if q.get("status") == "aktiv")

    prompt = (
        f"Du är en krönikör som sammanfattar ett kapitel i ett D&D-äventyr.\n"
        f"Kapitelrubrik: {body.title}\n"
        f"Karaktär: {char_name}, Plats: {location}\n"
        f"NPCs: {npcs}\nAktiva uppdrag: {quests}\n\n"
        f"Senaste händelser:\n{t_text}\n\n"
        f"Skriv en stämningsfull kapitalsammanfattning (3-5 meningar) på svenska. "
        f"Använd rubriken '{body.title}'. Beskriv vad som hände och vad som väntar."
    )

    try:
        summary = await _call_llm(
            ATMOSPHERE_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=512,
        )
    except Exception:
        summary = f"Kapitel {body.title}: Äventyret fortsätter i {location}. Mörkret väntar."

    # Spara sammanfattning och öka kapitelräknaren
    store.save_summary(state, summary)
    state["meta"]["chapter_count"] = state["meta"].get("chapter_count", 0) + 1
    store.save(state)

    return {"ok": True, "title": body.title, "summary": summary, "chapter_count": state["meta"]["chapter_count"]}


# ═══════════════════════════════════════
# CHAT
# ═══════════════════════════════════════


def compact_state(state: dict) -> str:
    """Kompakt naturligt-språk-sammanfattning av kampanjtillståndet.

    Ersätter json.dumps i DM-prompten — ger LLM:n samma information
    till en bråkdel av tokenkostnaden.
    """
    char = state.get("character", {})
    name = char.get("name", "Okänd")
    klass = char.get("class", "Äventyrare")
    level = char.get("level", 1)
    hp = char.get("hp", {})
    hp_cur = hp.get("current", 0)
    hp_max = hp.get("max", 0)
    ac = char.get("ac", 10)
    currency = state.get("currency", {})
    wallet = currency_display(currency)
    coin_wt = currency_weight(currency)

    lines = [f"{name}, {klass} niv {level}. HP {hp_cur}/{hp_max}. AC {ac}. Plånbok: {wallet}. Myntvikt: {coin_wt} lb."]

    # Utrustade föremål
    equipped = [it.get("name", "?") for it in state.get("inventory", []) if it.get("equipped")]
    if equipped:
        lines.append(f"Bär: {', '.join(equipped)}")

    # Plats, tid, dag
    world = state.get("world", {})
    loc = world.get("current_location", "Okänd")
    tid = world.get("time", "okänd")
    dag = world.get("day", 1)
    lines.append(f"Plats: {loc}. Tid: {tid}. Dag: {dag}.")

    # Fiender
    enemies = [n for n in state.get("npcs", []) if n.get("relation") == "fiende" and n.get("alive", True)]
    if enemies:
        e_str = ", ".join(f"{n.get('name', '?')} ({n.get('hp', '?')})" for n in enemies)
        lines.append(f"Fiender: {e_str}")
    else:
        lines.append("Fiender: inga")

    # Aktiva uppdrag
    active_quests = [q.get("name", "?") for q in state.get("quests", []) if q.get("status") == "aktiv"]
    if active_quests:
        lines.append(f"Aktiva uppdrag: {', '.join(active_quests)}")

    # Kända NPCs (max 10)
    npcs = state.get("npcs", [])
    if npcs:
        npc_strs = [
            f"{n.get('name', '?')} ({n.get('role', '?')}, {n.get('relation', '?')})"
            for n in npcs[:10]
        ]
        lines.append(f"Kända NPCs: {', '.join(npc_strs)}")

    return "\n".join(lines)


def truth_block(state: dict) -> str:
    """Auktoritär sanning — LLM:n får ALDRIG motsäga detta."""
    parts = ["## SANNING (auktoritär — motsäg ALDRIG detta)\n", compact_state(state)]

    pinned = state.get("pinned_facts", [])
    if pinned:
        parts.append("\nPinmade fakta:")
        for fact in pinned:
            parts.append(f"- {fact}")

    return "\n".join(parts)


def _build_system_prompt(
    state: dict,
    turn_override: int | None = None,
    awakening_trigger: bool = False,
    player_input: str = "",
    guardian_roll: dict | None = None,
) -> str:
    """Bygg systemprompt med kampanjkontext. turn_override används av /api/chat
    för att räkna med det meddelande som ännu inte sparats i transkriptet."""
    # Core-prompt + version (versionen tvingar cache-miss vid ändringar)
    # ── LANGUAGE FIRST: must come before everything else ──
    lang = _get_lang(state)
    if lang == "en":
        parts = [
            "[LANGUAGE: ENGLISH] You MUST write ALL narration, dialogue, NPC speech, "
            "descriptions, and every single word of your response in English. "
            "This overrides any Swedish text in the instructions below — those are "
            "internal system notes, NOT the output language.\n"
        ]
    else:
        parts = [
            "[SPRÅK: SVENSKA] Du MÅSTE skriva ALL narration, dialog, NPC-repliker, "
            "beskrivningar och varje ord i ditt svar på svenska.\n"
        ]
    parts.append(f"[DM-prompt {DM_PROMPT_VERSION}]\n" + DM_CORE_PROMPT)

    # Combat vs Narrative — injicera bara det som behövs denna tur
    enemies = [n for n in state.get("npcs", []) if n.get("relation") == "fiende" and n.get("alive", True)]
    if enemies:
        parts.append(DM_COMBAT_PROMPT)
    else:
        parts.append(DM_NARRATIVE_PROMPT)

    # Sanning — kompakt tillstånd istället för rå JSON
    parts.append("\n" + truth_block(state))

    # Hierarkiska sammanfattningar: 2 scen + 2 kapitel + 1 kampanjbåge
    scene_summaries = store.load_summaries(state, last_n=2)
    for s in scene_summaries:
        parts.append(f"\n[Scen-sammanfattning vid tur {s.get('turn', '?')}]: {s.get('text', '')}")
    chapter_summaries = store.load_chapters(state, last_n=2)
    for c in chapter_summaries:
        parts.append(f"\n[Kapitel {c.get('chapter', '?')}]: {c.get('text', '')}")
    campaign_arcs = store.load_campaign_arcs(state, last_n=1)
    for a in campaign_arcs:
        parts.append(f"\n[Kampanjbåge {a.get('arc', '?')}]: {a.get('text', '')}")

    # Förra turens mekaniska händelser
    last_effects = state.get("meta", {}).get("last_effects")
    if last_effects:
        fx_labels = {
            "skada": "Skada", "hela": "Hela", "xp": "XP", "guld": "Guld",
            "föremål": "Nytt föremål", "föremål_bort": "Föremål bort",
            "quest": "Nytt uppdrag", "quest_slutförd": "Uppdrag slutfört",
            "quest_misslyckad": "Uppdrag misslyckat", "konsekvens": "Konsekvens",
            "npc_död": "NPC död", "plats": "Ny plats", "tid": "Tid",
            "npc_relation": "NPC-relation", "ny_dag": "Ny dag", "level_up": "Nivå upp",
        }
        fx_strs = [f"{fx_labels.get(e.get('type', ''), e.get('type', '?'))}: {e.get('value', '?')}" for e in last_effects]
        parts.append("\n## Förra turens händelser\n" + ", ".join(fx_strs))

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

    # ── Enforcement borttaget (v19) ──
    # tag_streak, missing_roll_streak, turns_since_roll: Guardian pre-DM
    # detekterar kast och post-DM extraherar mekanik. DM behöver inte påminnas.

    # Resultat-påminnelse: spelaren har skickat ett tärningsresultat.
    if player_input.strip().startswith("[Resultat:"):
        parts.append(
            "\n## 🎲 TÄRNINGSRESULTAT MOTTAGET\n"
            "Spelaren har slagit en tärning. Ge utfallet direkt:\n"
            "1. Jämför mot DC/AC → LYCKADES eller MISSLYCKADES.\n"
            "2. Berätta utfallet narrativt.\n"
            "3. ALDRIG fråga 'vad gör du?' utan att FÖRST ge utfallet."
        )

    # ── VAKNANDEPROTOKOLLET ──
    # Aktiveras av awakening-flaggan (nya kampanjer) eller av triggern.
    # turn_override = turn_count + det meddelande som ännu inte sparats.
    # turn==1 = spelarens första meddelande → DM ställer frågor.
    # turn==2 = spelaren har svarat på frågorna → DM öppnar scenen med svaren.
    meta = state.get("meta", {})
    if meta.get("awakening") or awakening_trigger:
        turn = turn_override if turn_override is not None else meta.get("turn_count", 0)
        default_opening = ("Describe the surroundings atmospherically and let the player explore."
                           if lang == "en" else
                           "Beskriv omgivningen atmosfäriskt och låt spelaren utforska.")
        opening = meta.get("opening_style", default_opening)
        if awakening_trigger or turn == 1:
            parts.append(AWAKENING_ASK_EN if lang == "en" else AWAKENING_ASK)
        elif turn == 2:
            tmpl = AWAKENING_OPEN_EN if lang == "en" else AWAKENING_OPEN
            parts.append(tmpl.format(opening_style=opening))

    # Per-turs regelinjicering — relevanta D&D 5e-regler för denna tur
    rules_text = inject_rules(player_input)
    if rules_text:
        parts.append(f"\n## RELEVANTA REGLER (denna tur)\n{rules_text}")

    # ── Guardian-råd: kast-detektion ──
    # Guardian har analyserat spelarens handling och rekommenderar ett kast.
    # DM:n bör använda exakt denna [KAST:]-tagg (eller motivera varför inte).
    if guardian_roll:
        parts.append(
            f"\n## 🛡️ GUARDIAN: KAST REKOMMENDERAS\n"
            f"Spelarens handling kräver ett tärningskast.\n"
            f"Använd: [KAST: {guardian_roll['notation']} | {guardian_roll['label']}]\n"
            f"Bygg scenen så att kastet känns naturligt. Ge konsekvenser för både lyckat och misslyckat."
        )

    return "\n".join(parts)


async def _retrieve_relevant_memory(
    username: str, campaign_id: str, query: str, state: dict
) -> str:
    """Hämta relevant långtidsminne via RAG + faktaregister.
    Returnerar en textblock som injiceras i systemprompten."""
    sections = []

    # 1. Faktaregister — keyword-baserat, alltid tillgängligt (ingen Qdrant krävs)
    try:
        register = FactRegister(username, campaign_id)
        relevant = register.get_relevant_facts(query, limit=8)
        if relevant:
            sections.append(format_facts_block(relevant))
    except Exception as e:
        logger.debug("Faktaregister ej tillgängligt: %s", e)

    # 2. RAG — semantisk sökning i Qdrant (transkript, lore, sammanfattningar)
    try:
        if await rag.qdrant_healthy():
            chunks = await rag.retrieve(query, username, top_k=4, campaign_id=campaign_id)
            if chunks:
                rag_lines = []
                for c in chunks:
                    label = {"transcript": "📜", "lore": "📖", "summary": "📋", "fact": "📌"}.get(
                        c.get("chunk_type", ""), "•"
                    )
                    rag_lines.append(f"{label} (tur {c.get('turn', '?')}, relevans {c.get('score', 0):.0%}): {c['text'][:200]}")
                sections.append(
                    "## RELEVANT HISTORIK (semantiskt minne)\n"
                    + "\n".join(rag_lines)
                )
    except Exception as e:
        logger.debug("RAG ej tillgängligt: %s", e)

    return "\n\n".join(sections)


# ── Bakgrund: generera dag-entry för loggboken ──
async def _generate_day_entry(username: str, campaign_id: str, prev_day: int) -> None:
    """Generera en dag-entry för föregående dag via snabb LLM.
    Körs i bakgrunden efter NY_DAG — blockerar aldrig HTTP-svaret."""
    try:
        st = store.get(username)
        if not st:
            return
        world = st.setdefault('world', {})
        transcript = store.load_transcript(st, last_n=200)
        start_idx = world.get('last_day_turn', 0)
        recent = transcript[start_idx:]
        if not recent:
            world['last_day_turn'] = len(transcript)
            world.pop('_pending_day_entry', None)
            store.save(st)
            return
        t_text = "\n".join(f"{e['role']}: {e['content']}" for e in recent)
        prompt = (
            "Här är transkriptet sedan förra dagsskiftet. "
            "Skriv en kort dag-entry (JSON): "
            '{"day": N, "title": "...", "mood": "...", '
            '"events": ["...", "..."], "location": "...", '
            '"npcs_met": [...], "quests": [...]}. '
            f"Dagnumret är {prev_day}. "
            "Max 3 events, max 2 NPCs. Svara ENDAST med JSON.\n\n"
            + t_text
        )
        raw = await _call_llm(
            EXTRACTION_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
            timeout=30,
        )
        entry = _extract_json(raw)
        entry['day'] = prev_day  # säkerställ korrekt dagnummer
        logbook = world.setdefault('logbook', {})
        days = logbook.setdefault('days', [])
        days.append(entry)
        world['last_day_turn'] = len(transcript)
        world.pop('_pending_day_entry', None)
        store.save(st)
        logger.info("📖 Dag-entry genererad för dag %d", prev_day)
    except Exception as e:
        logger.warning("📖 Dag-entry misslyckades: %s", e)



# ── Guardian POST-DM: kör i bakgrunden, blockerar ALDRIG HTTP-svaret ──
async def _guardian_post_dm(
    username: str, reply: str, player_msg: str,
    effective_turn: int, dm_npcs: list[dict],
) -> None:
    """Extraherar mekanik ur DM-svaret i bakgrunden.
    Uppdaterar state, sparar Guardian-rapport i transkriptet.
    Frontend pollar transkriptet för att visa rapporten."""
    try:
        state = store.get(username)
        if not state:
            return
        meta = state.setdefault("meta", {})
        turn_count = meta.get("turn_count", 0)

        _tg = time.time()
        _guardian_transcript = store.load_transcript(state, last_n=8)
        mech = await guardian_extract_mechanics(
            reply, player_msg, state, effective_turn,
            lambda msgs: _call_llm(GUARDIAN_MODEL, msgs, temperature=0.2, max_tokens=1500),
            language=_get_lang(state),
            conversation_history=_guardian_transcript,
        )
        guardian_effects = apply_mechanics(state, mech)

        # ASCII-art (avstängd tills vidare)
        if ATMOSPHERE_ENABLED:
            guardian_art = mech.get("ascii_art")
            if guardian_art and should_generate_art(meta, turn_count):
                meta["last_art_turn"] = turn_count
                logger.info("🛡️ Guardian-art (%.1fs)", time.time() - _tg)

        if guardian_effects:
            existing = meta.get("last_effects", [])
            existing_keys = {(e.get("type"), str(e.get("value"))) for e in existing}
            for ge in guardian_effects:
                key = (ge.get("type"), str(ge.get("value")))
                if key not in existing_keys:
                    existing.append(ge)
            meta["last_effects"] = existing

        guardian_summary = format_guardian_summary(
            guardian_effects, state,
            language=_get_lang(state),
            mech=mech,
            dm_npcs=dm_npcs,
            turn=effective_turn,
        )
        if guardian_summary:
            state = store.append_message(state, "guardian", guardian_summary)
            logger.info("🛡️ Guardian bakgrund (%.1fs): %d effekter, %d DM-NPCs, loggbok=%s",
                        time.time() - _tg, len(guardian_effects), len(dm_npcs),
                        "ja" if mech.get("logbook") else "nej")
        else:
            logger.info("🛡️ Guardian bakgrund (%.1fs): inga ändringar", time.time() - _tg)

        store.save(state)
    except Exception as e:
        logger.warning("🛡️ Guardian bakgrund hoppade över: %s", e, exc_info=True)


# ── Bakgrundsuppgifter efter ett DM-svar (icke-kritiska, blockerar ALDRIG svaret) ──
async def _post_turn_tasks(
    username: str, campaign_id: str, reply: str, player_msg: str,
    turn_count: int, model_id: str,
) -> None:
    """Körs i bakgrunden EFTER att HTTP-svaret skickats till klienten.
    Faktextraktion, RAG-indexering och sammanfattning — inget av detta
    får någonsin fördröja spelarens upplevelse. Alla fel sväljs tyst."""
    # 1. Extrahera fakta + inventory-ändringar ur DM-svaret (billig modell)
    try:
        async def _extraction_llm(messages: list[dict]) -> str:
            return await _call_llm(EXTRACTION_MODEL, messages, temperature=0.2, max_tokens=800)

        # Bygg inventory-lista för kontext (så LLM:n inte lägger till duplikat)
        st = store.get(username)
        inv_names = []
        if st:
            for it in st.get("inventory", []):
                inv_names.append(f"- {it['name']} (×{it.get('qty', 1)})")
        inv_list_str = "\n".join(inv_names) if inv_names else "(tomt)"

        facts, inv_changes = await extract_facts(
            reply, player_msg, turn_count, _extraction_llm,
            inventory_list=inv_list_str,
            language=_get_lang(st) if st else "en",
        )
        if facts:
            register = FactRegister(username, campaign_id)
            register.add_facts(facts)
            logger.info("Extraherade %d fakta (tur %d)", len(facts), turn_count)

        # Applicera inventory-ändringar (LLM-baserat säkerhetsnät)
        if inv_changes and st:
            inv = st.setdefault("inventory", [])
            # Namn som redan lagts till via [FÖREMÅL:]-tagg denna tur
            tag_added = {e["value"].lower() for e in (st.get("meta", {}).get("last_effects", []))
                         if e.get("type") == "föremål"}
            for ch in inv_changes:
                name_lower = ch["name"].lower()
                if ch["action"] == "add":
                    # Skippa om taggen redan lade till det
                    if name_lower in tag_added:
                        logger.debug("📦 LLM-extraktion skippade '%s' (redan taggad)", ch["name"])
                        continue
                    existing = next((it for it in inv if it["name"].lower() == name_lower), None)
                    if existing:
                        existing["qty"] = existing.get("qty", 1) + ch["qty"]
                        logger.info("📦 LLM-dedup: '%s' → qty=%d", ch["name"], existing["qty"])
                    else:
                        inv.append({
                            "id": f"llm-{len(inv)}",
                            "name": ch["name"],
                            "type": ch.get("type", "Annat"),
                            "qty": ch["qty"],
                            "weight": 0,
                            "equipped": False,
                            "rarity": "normal",
                            "description": "",
                        })
                        logger.info("📦 LLM-extraktion lade till '%s'", ch["name"])
                elif ch["action"] == "remove":
                    existing = next((it for it in inv if it["name"].lower() == name_lower), None)
                    if existing:
                        existing["qty"] = existing.get("qty", 1) - ch["qty"]
                        if existing["qty"] <= 0:
                            inv.remove(existing)
                            logger.info("📦 LLM-extraktion tog bort '%s'", ch["name"])
                        else:
                            logger.info("📦 LLM-extraktion minskade '%s' → qty=%d", ch["name"], existing["qty"])
            store.save(st)
    except Exception as e:
        logger.debug("Faktextraktion hoppade över: %s", e)

    # 1b. Guardian POST-DM: flyttad till /api/chat (inline) — syns nu i chatten.

    # 2. Indexera senaste transkriptet i Qdrant (var 5:e tur)
    if turn_count % 5 == 0 and turn_count > 0:
        try:
            if await rag.qdrant_healthy():
                st = store.get(username)
                if st:
                    recent = store.load_transcript(st, last_n=10)
                    msgs_for_rag = [
                        {"role": e["role"], "content": e["content"], "turn": turn_count}
                        for e in recent
                        if e.get("content") != "__VAKNA_DM__"
                    ]
                    if msgs_for_rag:
                        await rag.index_transcript(msgs_for_rag, username, campaign_id)
                        logger.info("RAG-indexerade %d meddelanden (tur %d)", len(msgs_for_rag), turn_count)
        except Exception as e:
            logger.debug("RAG-indexering hoppade över: %s", e)

    # 3. Sammanfattning (om det är dags)
    try:
        st = store.get(username)
        if st and store.maybe_summarize(st):
            full_transcript = store.load_transcript(st, last_n=60)
            t_text = "\n".join(f"{e['role']}: {e['content']}" for e in full_transcript)
            sum_prompt = (
                "Sammanfatta följande D&D-session på svenska. "
                "Fokusera på viktiga händelser, beslut, NPC-möten och konsekvenser. "
                "Max 200 ord.\n\n" + t_text
            )
            summary = await _call_llm(
                EXTRACTION_MODEL, [{"role": "user", "content": sum_prompt}],
                temperature=0.3, max_tokens=512,
            )
            store.save_summary(st, summary)
            logger.info("Sammanfattning sparad (tur %d)", turn_count)
    except Exception as e:
        logger.debug("Sammanfattning hoppade över: %s", e)

    # 4. Kapitel-sammanfattning (var 5:e scen-sammanfattning, Nivå 2)
    try:
        st = store.get(username)
        if st and store.maybe_chapter(st):
            scenes = store.load_summaries(st, last_n=5)
            s_text = "\n\n".join(
                f"Scen {i + 1}: {s.get('text', '')}"
                for i, s in enumerate(scenes)
            )
            ch_prompt = (
                "Sammanfatta följande fem scener till ETT kapitel på svenska. "
                "Fokusera på övergripande händelsebåge, viktiga beslut, NPC-utveckling "
                "och konsekvenser. Max 300 ord.\n\n" + s_text
            )
            chapter_text = await _call_llm(
                EXTRACTION_MODEL, [{"role": "user", "content": ch_prompt}],
                temperature=0.3, max_tokens=512, timeout=30,
            )
            store.save_chapter_summary(st, chapter_text)
            logger.info("Kapitel-sammanfattning sparad (tur %d)", turn_count)
    except Exception as e:
        logger.debug("Kapitel-sammanfattning hoppade över: %s", e)

    # 5. Kampanjbåge (var 3:e kapitel, Nivå 3)
    try:
        st = store.get(username)
        if st and store.maybe_arc(st):
            chapters = store.load_chapters(st, last_n=3)
            c_text = "\n\n".join(
                f"Kapitel {i + 1}: {c.get('text', '')}"
                for i, c in enumerate(chapters)
            )
            arc_prompt = (
                "Sammanfatta följande tre kapitel till EN kampanjbåge på svenska. "
                "Fokusera på den stora berättelsen, huvudkonflikter, allianser och "
                "hur världen förändrats. Max 400 ord.\n\n" + c_text
            )
            arc_text = await _call_llm(
                EXTRACTION_MODEL, [{"role": "user", "content": arc_prompt}],
                temperature=0.3, max_tokens=640, timeout=30,
            )
            store.save_campaign_arc(st, arc_text)
            logger.info("Kampanjbåge sparad (tur %d)", turn_count)
    except Exception as e:
        logger.debug("Kampanjbåge hoppade över: %s", e)


@app.post("/api/chat")
async def chat(req: ChatRequest, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj — skapa en först")

    # Spelaren svarade på ett tärningskast → rensa väntande kast-begäran.
    # last_roll_requests fungerar då som "obesvarade kast": de finns kvar
    # tills spelaren slår, så en refresh kan återställa knapparna.
    if req.message.startswith("[Resultat:"):
        state.setdefault("meta", {})["last_roll_requests"] = []

    # Bygg meddelandelista — spelarens meddelande sparas först EFTER att LLM:n svarat,
    # så ett misslyckat anrop lämnar inga spår i transkriptet.
    effective_turn = state["meta"].get("turn_count", 0) + 1
    is_awakening = req.message == "__VAKNA_DM__"
    _t0 = time.time()
    logger.info(
        "▶ TUR %d · modell=%s · %s",
        effective_turn, req.model_id,
        "VAKNANDE" if is_awakening else f"«{req.message[:40]}»",
    )

    # ── Guardian PRE-DM: kast-detektion ──
    # Guardian avgör om handlingen kräver ett kast och i så fall vilket.
    # Resultatet injiceras som råd i DM-prompten + fungerar som fallback
    # om DM glömmer [KAST:]-taggen.
    # Vi skickar med senaste DM-svar som kontext så Guardian förstår situationen.
    guardian_roll = None
    if not is_awakening and not req.message.startswith("[Resultat:"):
        try:
            _tg = time.time()
            # Hämta senaste DM-svar från transkriptet för kontext
            _recent = store.load_transcript(state, last_n=4)
            _dm_context = ""
            for entry in reversed(_recent):
                if entry.get("role") == "assistant":
                    _dm_context = entry.get("content", "")
                    break
            guardian_roll = await guardian_check_roll(
                req.message, state,
                lambda msgs: _call_llm(GUARDIAN_MODEL, msgs, temperature=0.1, max_tokens=200),
                language=_get_lang(state),
                dm_context=_dm_context,
            )
            if guardian_roll:
                logger.info("🛡️ Guardian pre-DM (%.1fs): kast %s (%s)",
                            time.time() - _tg, guardian_roll["notation"], guardian_roll["label"])
            else:
                logger.debug("🛡️ Guardian pre-DM (%.1fs): inget kast", time.time() - _tg)
        except Exception as e:
            logger.warning("🛡️ Guardian pre-DM hoppade över: %s", e)

    messages = [{"role": "system", "content": _build_system_prompt(
        state, turn_override=effective_turn, awakening_trigger=is_awakening,
        player_input=req.message,
        guardian_roll=guardian_roll,
    )}]
    logger.debug("Systemprompt byggd (%d tecken)", len(messages[0]["content"]))

    # RAG + faktaregister: injicera relevant långtidsminne i systemprompten
    if not is_awakening:
        campaign_id = state["meta"].get("campaign_id", "")
        try:
            _tm = time.time()
            memory_block = await _retrieve_relevant_memory(
                username, campaign_id, req.message, state
            )
            if memory_block:
                messages[0]["content"] += "\n\n" + memory_block
                logger.info("🧠 Minne injicerat (+%d tkn, %.1fs)", len(memory_block), time.time() - _tm)
            else:
                logger.debug("🧠 Inget relevant minne hittades (%.1fs)", time.time() - _tm)
        except Exception as e:
            logger.warning("RAG/fakta-injektion hoppade över: %s", e)

    # Sammanfattningar injiceras numera i _build_system_prompt (hierarkiskt:
    # 2 scen + 2 kapitel + 1 kampanjbåge) — ingen separat loop behövs här.

    # Lägg till recent transcript + spelarens nya meddelande
    # (vaknandetrigger filtreras bort — den är en intern signal, inte spelartext)
    transcript = store.load_transcript_by_tokens(state)
    for entry in transcript:
        if entry.get("content") == "__VAKNA_DM__":
            continue
        if entry["role"] == "guardian":
            # Guardian-rapport → DM ser den som systemkontext (mekaniska ändringar)
            messages.append({"role": "user", "content": f"[GUARDIAN: Mekaniska ändringar denna tur]\n{entry['content']}"})
        else:
            messages.append({"role": "user" if entry["role"] == "user" else "assistant", "content": entry["content"]})
    # Vaknandet: LLM:n ser en narrativ kallelse istället för den råa triggern
    user_content = req.message
    if is_awakening:
        user_content = "*Du slår upp ögonen i mörkret. Någon har kallat på dig. En ny spelare sitter vid bordet och väntar.*"
    messages.append({"role": "user", "content": user_content})
    logger.debug("Kontext: %d meddelanden → DM", len(messages))

    # Anropa LLM — vid fel: riktigt felmeddelande, ingen placeholder
    _tllm = time.time()
    reasoning = ""

    # ── Long-form detektion ──
    # Om spelaren ber om bakgrundshistoria, bokkapitel, detaljerad beskrivning etc.
    # höj max_tokens så DM får utrymme att skriva en längre berättelse.
    _long_form_kw = [
        "bakgrund", "berätta om", "historia", "kapitel", "läsa", "bok",
        "legend", "berättelse", "dagbok", "brev", "beskriv", "vad ser jag",
        "undersök", "inskription", "runor", "skylt", "karta", "musik",
        "sång", "dikt", "minne", "dröm", "vision", "förflutna",
        " backstory", "tell me about", "history", "chapter", "read", "book",
        "legend", "tale", "diary", "letter", "describe", "what do i see",
        "examine", "inscription", "runes", "sign", "map", "song", "poem",
        "memory", "dream", "vision", "past",
    ]
    _is_long_form = any(kw in req.message.lower() for kw in _long_form_kw) and len(req.message) > 15
    _dm_max_tokens = 4096 if _is_long_form else 1024
    if _is_long_form:
        logger.info("📖 Long-form request — max_tokens höjt till %d", _dm_max_tokens)

    try:
        reply, reasoning, usage = await _call_llm_with_reasoning(req.model_id, messages, max_tokens=_dm_max_tokens)
        _llm_time = round(time.time() - _tllm, 1)
        logger.info("🤖 DM svarade (%d tkn, %.1fs)", len(reply), _llm_time)
        if reasoning:
            logger.debug("💭 DM resonerade (%d tkn)", len(reasoning))
    except HTTPException:
        logger.error("❌ DM-anrop misslyckades (HTTP-fel)")
        raise
    except (ValueError, RuntimeError) as e:
        logger.error("❌ DM-anrop misslyckades: %s", e)
        raise HTTPException(502, f"DM:n nås inte just nu: {e}")
    except Exception as e:
        logger.error("❌ Oväntat LLM-fel: %s", e)
        raise HTTPException(502, f"Oväntat LLM-fel: {e}")

    # Spara spelarens meddelande + DM-svar i transkriptet
    state = store.append_message(state, "user", req.message)

    # Parsa NPCs och kastbegäran ur svaret
    reply, new_npcs = _parse_npcs(reply)
    reply, roll_requests = _parse_roll_requests(reply)
    if new_npcs:
        logger.info("🎭 %d ny(a) NPC: %s", len(new_npcs), ", ".join(n["name"] for n in new_npcs))
    if roll_requests:
        logger.info("🎲 %d kast begärt: %s", len(roll_requests), ", ".join(r["notation"] for r in roll_requests))

    # ── Säkerhetsnät: prosa-kast utan [KAST:]-tagg ──
    # Om DM skrev "Rulla tärningen" i prosa men glömde taggen spawnas ingen
    # klickbar tärning och spelaren fastnar. Auto-spawna en 1d20 så spelet
    # aldrig stannar. (Taggade kast har redan rensats ur reply av _parse_roll_requests.)
    if not roll_requests and PROSE_ROLL_PATTERN.search(reply):
        roll_requests = [{"notation": "1d20", "label": "Tärningsslag"}]
        logger.warning("🎲 Prosa-kast upptäckt (ingen [KAST:]-tagg) → auto-spawnar 1d20")

    # ── Guardian-fallback: DM glömde [KAST:] men Guardian rekommenderade kast ──
    # Guardian pre-DM avgjorde att handlingen kräver kast. Om DM inte
    # producerade någon [KAST:]-tagg, använd Guardians rekommendation.
    if not roll_requests and guardian_roll:
        roll_requests = [{"notation": guardian_roll["notation"], "label": guardian_roll["label"]}]
        logger.warning("🛡️ Guardian-fallback: DM glömde [KAST:] → auto-spawnar %s (%s)",
                       guardian_roll["notation"], guardian_roll["label"])

    # Lägg till nya NPCs FÖRE taggparsning (så NPC_DÖD hittar dem)
    for npc in new_npcs:
        existing = {n.get("name", "").lower() for n in state.get("npcs", [])}
        if npc["name"].lower() not in existing:
            state.setdefault("npcs", []).append(npc)

    # ── Pydantic-validering + retry av mekaniska taggar ──
    # Parsa mekaniska taggar och validera mot kampanjtillståndet. Vid fel:
    # repair-prompt + nytt LLM-anrop (upp till 2 försök totalt). Efter 2
    # misslyckade försök behålls narrationen men trasig mekanik förkastas.
    effects: list = []
    dm_valid = True
    base_state = copy.deepcopy(state)  # utgångsläge innan mekanisk parsning
    current_reply = reply
    last_errors: list[str] = []

    for attempt in range(2):
        work_state = copy.deepcopy(base_state)
        parsed_reply, work_state, parsed_effects = _parse_mechanical_tags(
            current_reply, work_state
        )
        dm_resp, errors = validate_dm_response(
            parsed_reply, parsed_effects, roll_requests, work_state
        )
        if dm_resp.valid:
            # Giltigt — acceptera parsningen
            state = work_state
            reply = parsed_reply
            effects = parsed_effects
            dm_valid = True
            last_errors = []
            break

        last_errors = errors
        if attempt < 1:
            # Ogiltigt — be LLM:n reparera de mekaniska taggarna
            repair_prompt = (
                "Ditt förra svar hade dessa fel: "
                + "; ".join(errors)
                + ". Behåll narrationen men fixa de mekaniska taggarna. "
                "Svara med samma format."
            )
            try:
                repaired = await _call_llm(
                    req.model_id,
                    messages
                    + [
                        {"role": "assistant", "content": current_reply},
                        {"role": "user", "content": repair_prompt},
                    ],
                )
                # Rensa NPC-/kast-taggar ur det reparerade svaret (texten bara)
                repaired, _ = _parse_npcs(repaired)
                repaired, _ = _parse_roll_requests(repaired)
                current_reply = repaired
            except Exception as e:
                logger.warning("Repair-anrop misslyckades: %s", e)
                break
        else:
            # Försöken slut — behåll narrationen, förkasta trasig mekanik
            logger.warning(
                "DM-svar ogiltigt efter 2 försök, förkastar mekanik. Fel: %s",
                "; ".join(errors),
            )
            reply = _strip_mechanical_tags(current_reply)
            effects = []
            dm_valid = False

    # ── Prosa-föremål: borttaget (v18) ──
    # LLM-extraktion i _post_turn_tasks() hanterar nu föremål som DM
    # glömde tagga — med kontextförståelse istället för regex.

    # Spara effekter för nästa turs systemprompt
    meta = state.setdefault("meta", {})
    meta["last_effects"] = effects if effects else []
    # Spara kast-begäran så transkript-fallbacken kan återställa dem
    meta["last_roll_requests"] = roll_requests if roll_requests else []

    # ── ASCII-art: Guardian genererar i post-DM (se guardian_inline nedan) ──
    # Fallback-banken används om Guardian inte genererade art.
    ascii_art = None
    art_type = None
    event_art_type = None
    turn_count = meta.get("turn_count", 0)

    # Rensa intern struktur innan transkriptsparning
    # (reply är redan rensad från mekaniska taggar via _parse_mechanical_tags)
    reply = re.sub(r'<STATE_UPDATE>.*?</STATE_UPDATE>', '', reply, flags=re.DOTALL).strip()
    # Säkerhetsnät: reasoning-modeller kan läcka <think>-taggar i content
    reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL | re.IGNORECASE).strip()
    # Prosa-kast som säkerhetsnätet missade (t.ex. "Kast:" som rubrik)
    if not roll_requests and re.search(r'^\s*-?\s*Kast\s*:', reply, re.MULTILINE | re.IGNORECASE):
        roll_requests = [{"notation": "1d20", "label": "Tärningsslag"}]
        reply = re.sub(r'^\s*-?\s*Kast\s*:.*$', '', reply, flags=re.MULTILINE | re.IGNORECASE).strip()
        logger.warning("🎲 Prosa-kast 'Kast:' upptäckt → auto-spawnar 1d20")

    # Spara DM-svar (ren text — inga taggar eller intern struktur)
    state = store.append_message(state, "assistant", reply, meta={
        "model": req.model_id,
        "tokens": usage,
        "time": _llm_time,
    })

    # ── Spara DM-svar + effekter (Guardian kör i bakgrunden) ──
    store.save(state)

    # ── Guardian POST-DM → BAKGRUND (blockerar ALDRIG HTTP-svaret) ──
    guardian_task = asyncio.create_task(_guardian_post_dm(
        username, reply, req.message, effective_turn, list(new_npcs),
    ))
    _BACKGROUND_TASKS.add(guardian_task)
    guardian_task.add_done_callback(_BACKGROUND_TASKS.discard)

    # ── Fas 3: Faktextraktion + RAG + sammanfattning → BAKGRUND ──
    # Dessa är icke-kritiska och får ALDRIG fördröja HTTP-svaret till klienten.
    # (Tidigare blockerade de svaret i upp till 180s vardera → "fastnar i laddning".)
    campaign_id = state["meta"].get("campaign_id", "")
    turn_count = state["meta"].get("turn_count", 0)
    task = asyncio.create_task(_post_turn_tasks(
        username, campaign_id, reply, req.message, turn_count, req.model_id,
    ))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    # Dag-entry: om NY_DAG trigga, generera loggbok-entry i bakgrunden
    if state.get('world', {}).pop('_pending_day_entry', False):
        prev_day = state['world']['day'] - 1
        day_task = asyncio.create_task(_generate_day_entry(username, campaign_id, prev_day))
        _BACKGROUND_TASKS.add(day_task)
        day_task.add_done_callback(_BACKGROUND_TASKS.discard)

    logger.info("◀ TUR %d klar · totalt %.1fs", state["meta"]["turn_count"], time.time() - _t0)

    return {
        "reply": reply,
        "reasoning": reasoning[:3000] if reasoning else "",
        "model_id": req.model_id,
        "tokens": usage,
        "response_time": _llm_time,
        "turn_count": state["meta"]["turn_count"],
        "summary_generated": False,  # körs nu i bakgrunden
        "new_npcs": new_npcs,
        "roll_requests": roll_requests,
        "ascii_art": ascii_art,
        "art_type": art_type,
        "effects": effects,
        "guardian_summary": "",
        "guardian_pending": True,
    }


# ═══════════════════════════════════════
# CHARACTER GENERATION
# ═══════════════════════════════════════

CHARACTER_PROMPT_SV = """Du är en D&D-karaktärsgenerator för ett mörkt fantasy-äventyr. Skapa en karaktär baserad på spelarens beskrivning.

VIKTIGT: Karaktären hör hemma i en PÅHITTAD fantasy-värld. Använd ALDRIG verkliga ortsnamn (inga svenska städer, länder eller kända platser) i namn, bakgrund eller utrustning. Hitta på stämningsfulla fantasy-namn.

Svara ENDAST med giltig JSON (ingen markdown) med detta schema:
{
  "name": "string",
  "race": "string",
  "class": "string",
  "level": 1,
  "alignment": "string",
  "background": "string — klass/bakgrund, kort",
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
  "traits": ["string — 3-4 förmågor/egenskaper"],
  "saves": [],
  "gear": "string — startutrustning, 5-8 föremål separerade med ' · '",
  "story": "string — bakgrundshistoria, max 100 ord, mörk och stämningsfull",
  "inventory": [
    {"name": "string", "type": "Vapen|Rustning|Dryck|Magisk|Verktyg|Annat", "qty": 1, "weight": 1.0, "equipped": false, "rarity": "normal|magic|rare|legendary", "damage": "1d8 slashing|null", "damage_dice": "1d8|null", "damage_type": "slashing|null", "ac_bonus": 14|null, "range": "melee|null", "properties": ["versatile"], "magic_bonus": 0, "charges": null, "max_charges": null, "description": "string", "effects": "string|null"}
  ]
}

## STARTUTRUSTNING (inventory) — KRITISKT
Fyll ALLTID inventory-arrayen med 5-8 föremål som passar karaktärens klass och bakgrund:
- **Ett basvapen** som passar klassen (svärd för krigare, stav för magiker, dolk för rogue, etc.) — sätt equipped:true. Fyll i damage (t.ex. "1d8 slashing"), damage_dice, damage_type, range ("melee" eller "ranged X/Y"), properties (t.ex. ["finesse","light"]).
- **Rustning** (om relevant): fyll i ac_bonus (t.ex. 14 för kedjerustning, 11+DEX för läder). Sköld: ac_bonus=2, type="Rustning".
- **Mat/proviant** (t.ex. "Torkat kött", "Hårt bröd", "Fältportioner") — qty 2-5
- **En potion** (t.ex. "Läkedryck", "Elixir av mod", "Giftflaska") — qty 1-2. Magiska föremål/potions: fyll i charges, max_charges, effects, magic_bonus.
- **Ett klass-unikt föremål** som speglar klassens identitet (t.ex. "Runristad spellbok" för magiker, "Tjuvverktyg" för rogue, "Heligt symbol" för cleric, "Jaktbåge + 20 pilar" för ranger)
- **2-3 ytterligare äventyrsföremål** (rep, facklor, tändstål, karta, sovsäck, etc.)
- Sätt realistic weight (lbs) på varje föremål. Vapen 2-6 lbs, potion 0.5 lbs, mat 0.5-1 lbs per styck.
- Basvapnet ska ha equipped:true, allt annat equipped:false.
- rarity: de flesta "normal", potion kan vara "magic", det klass-unika föremålet kan vara "rare"."""

CHARACTER_PROMPT_EN = """You are a D&D character generator for a dark fantasy adventure. Create a character based on the player's description.

IMPORTANT: The character belongs in a FICTIONAL fantasy world. NEVER use real place names (no real cities, countries, or known locations) in names, backgrounds, or equipment. Invent atmospheric fantasy names.

Respond ONLY with valid JSON (no markdown) using this schema:
{
  "name": "string",
  "race": "string",
  "class": "string",
  "level": 1,
  "alignment": "string",
  "background": "string — class/background, brief",
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
  "traits": ["string — 3-4 abilities/traits"],
  "saves": [],
  "gear": "string — starting equipment, 5-8 items separated by ' · '",
  "story": "string — backstory, max 100 words, dark and atmospheric",
  "inventory": [
    {"name": "string", "type": "Weapon|Armor|Potion|Magic|Tool|Other", "qty": 1, "weight": 1.0, "equipped": false, "rarity": "normal|magic|rare|legendary", "damage": "1d8 slashing|null", "damage_dice": "1d8|null", "damage_type": "slashing|null", "ac_bonus": 14|null, "range": "melee|null", "properties": ["versatile"], "magic_bonus": 0, "charges": null, "max_charges": null, "description": "string", "effects": "string|null"}
  ]
}

## STARTING EQUIPMENT (inventory) — CRITICAL
ALWAYS fill the inventory array with 5-8 items fitting the character's class and background:
- **A base weapon** fitting the class (sword for fighter, staff for wizard, dagger for rogue, etc.) — set equipped:true. Fill in damage (e.g. "1d8 slashing"), damage_dice, damage_type, range ("melee" or "ranged X/Y"), properties (e.g. ["finesse","light"]).
- **Armor** (if relevant): fill in ac_bonus (e.g. 14 for chain mail, 11+DEX for leather). Shield: ac_bonus=2, type="Armor".
- **Food/rations** (e.g. "Dried meat", "Hard bread", "Field rations") — qty 2-5
- **A potion** (e.g. "Healing potion", "Elixir of courage", "Poison vial") — qty 1-2. Magic items/potions: fill in charges, max_charges, effects, magic_bonus.
- **A class-unique item** reflecting class identity (e.g. "Rune-etched spellbook" for wizard, "Thieves' tools" for rogue, "Holy symbol" for cleric, "Hunting bow + 20 arrows" for ranger)
- **2-3 additional adventure items** (rope, torches, tinderbox, map, bedroll, etc.)
- Set realistic weight (lbs) on each item. Weapons 2-6 lbs, potions 0.5 lbs, food 0.5-1 lbs per piece.
- The base weapon should have equipped:true, everything else equipped:false.
- rarity: most items "normal", potions can be "magic", the class-unique item can be "rare"."""


@app.post("/api/character/generate")
async def generate_character(req: CharacterRequest, morkrets_token: str | None = Cookie(None)):
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    # Språkanpassning av karaktärsgenerering
    lang = _get_lang(state)
    char_prompt = CHARACTER_PROMPT_EN if lang == "en" else CHARACTER_PROMPT_SV
    user_msg = f"Create a character: {req.prompt}" if lang == "en" else f"Skapa en karaktär: {req.prompt}"

    messages = [
        {"role": "system", "content": char_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw = await _call_llm(req.model_id, messages, temperature=0.7, max_tokens=4000, thinking_cap=8000)
        char_data = _extract_json(raw)
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        err = _err("Karaktären kunde inte vävas", "The character could not be woven", lang)
        raise HTTPException(502, f"{err}: {e}")

    # Validera löst — se till att grundfält finns
    if not char_data.get("name"):
        char_data["name"] = "Nameless" if lang == "en" else "Namnlös"
    for field in ("race", "class", "alignment", "background"):
        char_data.setdefault(field, "Unknown" if lang == "en" else "Okänd")
    char_data.setdefault("level", 1)
    char_data.setdefault("abilities", {})

    # Flytta startutrustning till state["inventory"] (där frontend läser den)
    inventory = char_data.pop("inventory", None)
    if isinstance(inventory, list) and inventory:
        # Normalisera varje föremål till frontend-formatet
        clean = []
        for it in inventory:
            if not isinstance(it, dict) or not it.get("name"):
                continue
            clean.append({
                "name": str(it["name"]),
                "type": str(it.get("type", "Other" if lang == "en" else "Annat")),
                "qty": int(it.get("qty", 1) or 1),
                "weight": float(it.get("weight", 1) or 1),
                "equipped": bool(it.get("equipped", False)),
                "rarity": str(it.get("rarity", "normal")),
            })
        state["inventory"] = clean

    state["character"] = char_data
    store.save(state)

    return {"ok": True, "character": char_data, "inventory": state.get("inventory", [])}


# ═══════════════════════════════════════
# KARAKTÄRSUPPDATERING + BILAGOR
# ═══════════════════════════════════════

ATTACHMENT_EXTS = {".pdf", ".md", ".txt"}
ATTACHMENT_MEDIA = {
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


@app.patch("/api/campaign/character")
async def update_character(req: dict, morkrets_token: str | None = Cookie(None)):
    """Uppdatera valda fält på den aktiva karaktären (t.ex. notes)."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    char = state.setdefault("character", {})
    # Tillåt bara kända fält (notes + framtida textfält) — aldrig abilities/hp
    for key in ("notes",):
        if key in req:
            char[key] = str(req[key])
    store.save(state)
    return {"ok": True, "character": char}


@app.patch("/api/campaign/inventory")
async def update_inventory(req: dict, morkrets_token: str | None = Cookie(None)):
    """Uppdatera hela inventory-listan (frontend skickar full array)."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    items = req.get("inventory")
    if not isinstance(items, list):
        raise HTTPException(400, "inventory måste vara en lista")

    # Normalisera varje föremål
    clean = []
    for it in items:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        clean.append({
            "id": str(it.get("id", f"item-{len(clean)}")),
            "name": str(it["name"]),
            "type": str(it.get("type", "Annat")),
            "qty": max(1, int(it.get("qty", 1))),
            "weight": max(0, float(it.get("weight", 1))),
            "equipped": bool(it.get("equipped", False)),
            "rarity": str(it.get("rarity", "normal")),
        })
    state["inventory"] = clean
    store.save(state)
    return {"ok": True, "inventory": clean}


@app.post("/api/campaign/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    morkrets_token: str | None = Cookie(None),
):
    """Ladda upp en bilaga (pdf/md/txt) till kampanjen."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    fname = file.filename or "bilaga.txt"
    ext = Path(fname).suffix.lower()
    if ext not in ATTACHMENT_EXTS:
        raise HTTPException(400, f"Filformat ej stöd: {ext} (tillåtna: .pdf, .md, .txt)")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Filen är för stor (max 5 MB)")

    cid = state["meta"]["campaign_id"]
    att_dir = CAMPAIGNS_DIR / username / cid / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)

    att_id = uuid.uuid4().hex[:12]
    # Spara med säkert filnamn men behåll originalnamnet i metadata
    safe_name = re.sub(r"[^\w.\-]", "_", fname)
    disk_name = f"{att_id}{ext}"
    (att_dir / disk_name).write_bytes(content)

    attachments = state.setdefault("attachments", [])
    entry = {
        "id": att_id,
        "name": fname,
        "disk_name": disk_name,
        "ext": ext,
        "size": len(content),
        "uploaded": datetime.now(timezone.utc).isoformat(),
    }
    attachments.append(entry)
    store.save(state)

    return {"ok": True, "attachment": entry}


@app.get("/api/campaign/attachments/{att_id}")
async def download_attachment(att_id: str, morkrets_token: str | None = Cookie(None)):
    """Ladda ner en bilaga."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    cid = state["meta"]["campaign_id"]
    entry = next((a for a in state.get("attachments", []) if a["id"] == att_id), None)
    if not entry:
        raise HTTPException(404, "Bilagan hittades inte")

    path = CAMPAIGNS_DIR / username / cid / "attachments" / entry["disk_name"]
    if not path.exists():
        raise HTTPException(404, "Fil saknas på disk")

    return FileResponse(
        path,
        media_type=ATTACHMENT_MEDIA.get(entry["ext"], "application/octet-stream"),
        filename=entry["name"],
    )


@app.delete("/api/campaign/attachments/{att_id}")
async def delete_attachment(att_id: str, morkrets_token: str | None = Cookie(None)):
    """Radera en bilaga."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    cid = state["meta"]["campaign_id"]
    attachments = state.get("attachments", [])
    entry = next((a for a in attachments if a["id"] == att_id), None)
    if not entry:
        raise HTTPException(404, "Bilagan hittades inte")

    path = CAMPAIGNS_DIR / username / cid / "attachments" / entry["disk_name"]
    if path.exists():
        path.unlink()

    state["attachments"] = [a for a in attachments if a["id"] != att_id]
    store.save(state)
    return {"ok": True, "message": "Bilagan raderad"}


# ═══════════════════════════════════════
# AVATARER — spelare, DM och NPCs
# ═══════════════════════════════════════

AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AVATAR_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _safe_avatar_key(kind: str) -> str:
    """Normalisera avatar-nyckel: 'player', 'dm' eller 'npc:<nyckel>'."""
    kind = (kind or "").strip()
    if kind in ("player", "dm"):
        return kind
    if kind.startswith("npc:"):
        key = kind[4:].strip()
        if key and re.fullmatch(r"[\w\-]+", key):
            return "npc:" + key
    raise HTTPException(400, f"Ogiltig avatar-typ: {kind}")


@app.post("/api/campaign/avatar")
async def upload_avatar(
    kind: str = Form(...),
    file: UploadFile = File(...),
    morkrets_token: str | None = Cookie(None),
):
    """Ladda upp en avatar för spelaren, DM eller en NPC."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    avatar_key = _safe_avatar_key(kind)

    fname = file.filename or "avatar.png"
    ext = Path(fname).suffix.lower()
    if ext not in AVATAR_EXTS:
        raise HTTPException(400, f"Filformat ej stöd: {ext} (tillåtna: png, jpg, webp, gif)")

    content = await file.read()
    if len(content) > 3 * 1024 * 1024:
        raise HTTPException(400, "Bilden är för stor (max 3 MB)")

    cid = state["meta"]["campaign_id"]
    av_dir = CAMPAIGNS_DIR / username / cid / "avatars"
    av_dir.mkdir(parents=True, exist_ok=True)

    disk_name = avatar_key.replace(":", "_") + ext
    (av_dir / disk_name).write_bytes(content)

    avatars = state.setdefault("avatars", {})
    avatars[avatar_key] = {
        "disk_name": disk_name,
        "ext": ext,
        "size": len(content),
        "uploaded": datetime.now(timezone.utc).isoformat(),
    }
    store.save(state)

    return {"ok": True, "kind": avatar_key, "url": f"/api/campaign/avatar/{avatar_key}"}


@app.get("/api/campaign/avatar/{kind:path}")
async def get_avatar(kind: str, morkrets_token: str | None = Cookie(None)):
    """Hämta en avatar-bild."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    avatar_key = _safe_avatar_key(kind)
    entry = state.get("avatars", {}).get(avatar_key)
    if not entry:
        raise HTTPException(404, "Avataren hittades inte")

    cid = state["meta"]["campaign_id"]
    path = CAMPAIGNS_DIR / username / cid / "avatars" / entry["disk_name"]
    if not path.exists():
        raise HTTPException(404, "Bild saknas på disk")

    return FileResponse(
        path,
        media_type=AVATAR_MEDIA.get(entry["ext"], "image/png"),
        headers={"Cache-Control": "no-cache"},
    )


@app.delete("/api/campaign/avatar/{kind:path}")
async def delete_avatar(kind: str, morkrets_token: str | None = Cookie(None)):
    """Ta bort en avatar (återgår till standard-sprite)."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]
    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    avatar_key = _safe_avatar_key(kind)
    avatars = state.get("avatars", {})
    entry = avatars.get(avatar_key)
    if not entry:
        raise HTTPException(404, "Avataren hittades inte")

    cid = state["meta"]["campaign_id"]
    path = CAMPAIGNS_DIR / username / cid / "avatars" / entry["disk_name"]
    if path.exists():
        path.unlink()

    del avatars[avatar_key]
    store.save(state)
    return {"ok": True, "message": "Avataren borttagen"}


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

VIKTIGT: Världen är en PÅHITTAD fantasy-värld. Om spelaren nämner verkliga ortsnamn (svenska städer, länder, kända platser), översätt dem till stämningsfulla fantasy-namn. Använd ALDRIG verkliga ortsnamn i output.

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


@app.get("/api/debug/logs")
async def debug_logs(
    since: float = 0.0,
    level: str | None = None,
    morkrets_token: str | None = Cookie(None),
):
    """🛠️ Maskinrummet — live-loggar för debug-konsolen.

    Query-parametrar:
      since  – bara loggar nyare än denna timestamp (polling)
      level  – filtrera: DEBUG | INFO | WARNING | ERROR (inkl. högre)
    Returnerar {logs: [...], now: <timestamp>} där 'now' skickas tillbaka
    som 'since' vid nästa poll. Kräver inloggning (ingen admin-gate —
    loggarna innehåller inga hemligheter, bara spelmekanik)."""
    _get_current_user(morkrets_token)
    min_level = _LOG_ORDER.get((level or "DEBUG").upper(), 10)
    out = [
        e for e in DEBUG_LOGS
        if e["ts"] > since and _LOG_ORDER.get(e["level"], 20) >= min_level
    ]
    return {"logs": out, "now": time.time(), "buffered": len(DEBUG_LOGS)}


@app.get("/api/campaign/locations")
async def campaign_locations(morkrets_token: str | None = Cookie(None)):
    """Returnera alla kända platser med restid från nuvarande position."""
    payload = _get_current_user(morkrets_token)
    state = store.get(payload["sub"])
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")
    locations = get_locations_with_travel(state)
    travel_log = state.get('world', {}).get('travel_log', [])
    return {"locations": locations, "travel_log": travel_log}


@app.get("/api/campaign/logbook")
async def campaign_logbook(morkrets_token: str | None = Cookie(None)):
    """Äventyrsjournal — cache-först, LLM bara vid första besöket."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    world = state.setdefault("world", {})

    # ── Cache-först: returnera direkt om dag-entries finns ──
    # Guardian sparar logbook som en array av {day, turn, text} i world["logbook"]
    # LLM-genererad logbook sparas som ett objekt {title, days, summary} i world["logbook_llm"]
    # Kontrollera båda formaten
    logbook_llm = world.get("logbook_llm", {})
    cached_days = logbook_llm.get("days", [])
    if cached_days:
        campaign_name = state.get("meta", {}).get("campaign_name", "Mörkrets Rike")
        return {
            "title": logbook_llm.get("title", campaign_name),
            "days": cached_days,
            "summary": logbook_llm.get("summary", ""),
            "generated_at": logbook_llm.get("generated_at", ""),
        }

    # ── Guardian-logbook: konvertera enkel {day, turn, text} → {days: [...]} ──
    guardian_log = world.get("logbook", [])
    if guardian_log and isinstance(guardian_log, list):
        # Gruppera per dag
        days_map = {}
        for entry in guardian_log:
            day = entry.get("day", 1)
            if day not in days_map:
                days_map[day] = {
                    "day": day,
                    "title": "",
                    "mood": "",
                    "events": [],
                    "location": "",
                    "npcs_met": [],
                    "quests": [],
                }
            days_map[day]["events"].append(entry.get("text", ""))

        days = sorted(days_map.values(), key=lambda d: d["day"])
        campaign_name = state.get("meta", {}).get("campaign_name", "Mörkrets Rike")

        # Om vi har Guardian-entries, returnera dem direkt (snabbt, inget LLM)
        if days and days[0]["events"]:
            summary_text = f"Äventyret har {len(days)} dag(ar) med {len(guardian_log)} händelser."
            return {
                "title": campaign_name,
                "days": days,
                "summary": summary_text,
            }

    # ── Första besöket: generera via LLM och cacha ──
    transcript = store.load_transcript(state, last_n=100)
    t_text = "\n".join(
        f"{e['role']}: {e['content']}" for e in transcript
    )

    summaries = store.load_summaries(state, last_n=10)
    s_text = "\n".join(
        f"[Tur {s['turn']}]: {s['text']}" for s in summaries
    )

    if not t_text and not s_text:
        return {"title": "Mörkrets Rike", "days": [], "summary": "Äventyret har inte börjat ännu."}

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
        log_data = {
            "title": campaign_name,
            "days": [{
                "day": 1,
                "title": "Äventyret börjar",
                "mood": "Förväntansfull",
                "events": ["Kampanjen skapades"],
                "location": world.get("current_location", "Okänd"),
                "npcs_met": [n.get("name", "?") for n in state.get("npcs", [])[:5]],
                "quests": [q.get("name", "?") for q in state.get("quests", []) if q.get("status") == "aktiv"],
            }],
            "summary": "Äventyret har just börjat. Mörkret väntar.",
        }

    # Cacha i world['logbook_llm'] — skiljt från Guardian's world['logbook']
    from datetime import datetime, timezone
    world["logbook_llm"] = {
        "title": log_data.get("title", campaign_name),
        "days": log_data.get("days", []),
        "summary": log_data.get("summary", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    store.save(state)

    return log_data


@app.post("/api/campaign/logbook/refresh-today")
async def campaign_logbook_refresh_today(morkrets_token: str | None = Cookie(None)):
    """Regenerera ENBART den senaste dag-entryn i loggboken."""
    payload = _get_current_user(morkrets_token)
    username = payload["sub"]

    state = store.get(username)
    if not state:
        raise HTTPException(404, "Ingen aktiv kampanj")

    world = state.setdefault("world", {})
    logbook = world.setdefault("logbook_llm", {})
    days = logbook.get("days", [])
    if not days:
        raise HTTPException(400, "Inga dag-entries att uppdatera")

    current_day = world.get("day", 1)
    last_entry = days[-1]
    target_day = last_entry.get("day", current_day)

    # Samla transkript sedan förra dagsskiftet
    transcript = store.load_transcript(state, last_n=200)
    start_idx = world.get("last_day_turn", 0)
    recent = transcript[start_idx:]
    t_text = "\n".join(f"{e['role']}: {e['content']}" for e in recent) if recent else ""

    if not t_text:
        return {"ok": False, "error": "Inget transkript tillgängligt"}

    prompt = (
        "Här är transkriptet sedan förra dagsskiftet. "
        "Skriv en kort dag-entry (JSON): "
        '{"day": N, "title": "...", "mood": "...", '
        '"events": ["...", "..."], "location": "...", '
        '"npcs_met": [...], "quests": [...]}. '
        f"Dagnumret är {target_day}. "
        "Max 3 events, max 2 NPCs. Svara ENDAST med JSON.\n\n"
        + t_text
    )

    try:
        raw = await _call_llm(
            EXTRACTION_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
            timeout=30,
        )
        new_entry = _extract_json(raw)
        new_entry["day"] = target_day
        days[-1] = new_entry
        logbook["days"] = days
        store.save(state)
        return {"ok": True, "entry": new_entry}
    except Exception as e:
        logger.warning("📖 Uppdatering av dag-entry misslyckades: %s", e)
        raise HTTPException(502, f"Kunde inte generera dag-entry: {e}")


# ═══════════════════════════════════════
# Admin Dashboard
# ═══════════════════════════════════════


def _require_admin(payload: dict):
    if payload.get("role") != "admin":
        raise HTTPException(403, "Admin-rättigheter krävs")


def _scan_user_transcripts(user: str) -> dict:
    """Skanna alla transkript för en användare och returnera token- och tursstatistik."""
    prompt_tokens = 0
    completion_tokens = 0
    turns = 0
    last_active = ""
    sessions = []

    user_dir = CAMPAIGNS_DIR / user
    if not user_dir.exists():
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "turns": 0, "last_active": "", "sessions": sessions}

    for campaign_dir in sorted(user_dir.iterdir()):
        if not campaign_dir.is_dir():
            continue
        transcript_dir = campaign_dir / "transcripts"
        if not transcript_dir.exists():
            continue
        campaign_id = campaign_dir.name
        for ts_file in sorted(transcript_dir.glob("session-*.jsonl")):
            session_prompt = 0
            session_completion = 0
            session_turns = 0
            session_last = ""
            try:
                with open(ts_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("role") == "assistant":
                            turns += 1
                            session_turns += 1
                        meta = entry.get("meta", {})
                        tokens = meta.get("tokens", {})
                        p = tokens.get("prompt_tokens", 0) or 0
                        c = tokens.get("completion_tokens", 0) or 0
                        prompt_tokens += p
                        completion_tokens += c
                        session_prompt += p
                        session_completion += c
                        ts = entry.get("ts", "")
                        if ts and ts > last_active:
                            last_active = ts
                        if ts and ts > session_last:
                            session_last = ts
            except OSError:
                continue
            sessions.append({
                "campaign_id": campaign_id,
                "session_file": ts_file.name,
                "prompt_tokens": session_prompt,
                "completion_tokens": session_completion,
                "total_tokens": session_prompt + session_completion,
                "turns": session_turns,
                "last_ts": session_last,
            })

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "turns": turns,
        "last_active": last_active,
        "sessions": sessions,
    }


@app.get("/api/admin/stats")
async def admin_stats(morkrets_token: str | None = Cookie(None)):
    """Admin-only: översikt av alla användare."""
    payload = _get_current_user(morkrets_token)
    _require_admin(payload)

    users = load_users()
    user_stats = []
    total_campaigns = 0
    total_tokens = 0
    total_turns = 0

    for username, udata in users.items():
        role = udata.get("role", "player") if isinstance(udata, dict) else "player"
        store = CampaignStore()
        campaigns = store.list_campaigns(username)
        scan = _scan_user_transcripts(username)
        total_campaigns += len(campaigns)
        total_tokens += scan["total_tokens"]
        total_turns += scan["turns"]
        user_stats.append({
            "username": username,
            "role": role,
            "total_campaigns": len(campaigns),
            "total_tokens": scan["total_tokens"],
            "prompt_tokens": scan["prompt_tokens"],
            "completion_tokens": scan["completion_tokens"],
            "total_turns": scan["turns"],
            "last_active": scan["last_active"],
        })

    return {
        "total_users": len(users),
        "total_campaigns": total_campaigns,
        "total_tokens": total_tokens,
        "total_turns": total_turns,
        "users": user_stats,
    }


@app.get("/api/admin/user/{username}")
async def admin_user_detail(username: str, morkrets_token: str | None = Cookie(None)):
    """Admin-only: detaljerad info om en specifik användare."""
    payload = _get_current_user(morkrets_token)
    _require_admin(payload)

    users = load_users()
    if username not in users:
        raise HTTPException(404, f"Användare '{username}' finns inte")

    store = CampaignStore()
    campaigns = store.list_campaigns(username)
    scan = _scan_user_transcripts(username)

    # Bygg per-kampanj token-uppdelning
    campaign_tokens = {}
    for s in scan["sessions"]:
        cid = s["campaign_id"]
        if cid not in campaign_tokens:
            campaign_tokens[cid] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "turns": 0, "sessions": []}
        campaign_tokens[cid]["prompt_tokens"] += s["prompt_tokens"]
        campaign_tokens[cid]["completion_tokens"] += s["completion_tokens"]
        campaign_tokens[cid]["total_tokens"] += s["total_tokens"]
        campaign_tokens[cid]["turns"] += s["turns"]
        campaign_tokens[cid]["sessions"].append(s)

    enriched = []
    for c in campaigns:
        cid = c["campaign_id"]
        ct = campaign_tokens.get(cid, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "turns": 0, "sessions": []})
        enriched.append({
            **c,
            "prompt_tokens": ct["prompt_tokens"],
            "completion_tokens": ct["completion_tokens"],
            "total_tokens": ct["total_tokens"],
            "turns": ct["turns"],
            "sessions": ct["sessions"],
        })

    return {
        "username": username,
        "role": users[username].get("role", "player") if isinstance(users[username], dict) else "player",
        "total_campaigns": len(campaigns),
        "total_tokens": scan["total_tokens"],
        "prompt_tokens": scan["prompt_tokens"],
        "completion_tokens": scan["completion_tokens"],
        "total_turns": scan["turns"],
        "last_active": scan["last_active"],
        "campaigns": enriched,
    }


# ═══════════════════════════════════════
# STATIC FILES — serva frontend
# ═══════════════════════════════════════
# Monteras EFTER alla /api/ routes så att API:et har prioritet.
# No-cache middleware för HTML/JS så att webbläsaren alltid hämtar senaste.

from starlette.middleware.base import BaseHTTPMiddleware

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(('.html', '.js')) or path == '/':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

app.add_middleware(NoCacheStaticMiddleware)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
