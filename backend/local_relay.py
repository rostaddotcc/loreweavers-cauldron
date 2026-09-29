"""
local_relay.py — 🏮 Local AI / Ollama relay (v1) for The Lore Weaver's Cauldron
================================================================================

Kärnprincip (design: ~/obsidian/vault/spel/dnd-llm-local-ollama-impl-2026-09.md):
**Servern är hjärnan, spelarens maskin är munnen.**

- ``prepare`` bygger DM-prompten server-side (Fas A av /api/chat) och lämnar
  Ollama-payloaden till klienten; steget sparas RAM-bundet mot
  (user, campaign, turn_count), TTL, engångsanvänt.
- Klienten anropar sin LOKALT körande Ollama (base_url lever bara i
  klientens localStorage — servern ser aldrig en användarstyrd URL ⇒ ingen
  SSRF-yta, inga secrets att stasha).
- ``commit`` kör efterbehandlingen (Fas B) på klientens text. Reläpathen
  konsumerar INTE någon hus-turn; istället bokförs en ledger-rad med
  ``action="local_dm", turns 0`` så admin ser aktivitet utan att driva potten.

Modell-id-konvention: ``local:<ollamamodell>`` — t.ex. ``local:qwen3:14b``
(följer or_free.py:s ``orfree:``-mönster). Servern måra ALDRIG anropa ett
local:-id: main._call_llm/_call_llm_with_reasoning/_stream_llm hårdavvisar
prefixet (defence-in-depth).

Env-flaggor (lästes vid anrop, inte import):
- LOCAL_AI_ENABLED         "1" slår på funktionen (default "0" ⇒ 503)
- LOCAL_STEP_TTL_SECONDS   stegens livstid (default 600 — hemma-hårdvara
                           behöver minuter, medvetet avsteg från skissens 120 s)
- LOCAL_DM_DAILY_CAP       max local_dm-kommenteringar/dag per konto (default 100)
"""

import os
import re
import secrets
import threading
import time

LOCAL_PREFIX = "local:"
# local:<ollamamodell> — Ollama-id tillåter bokstäver/siffror och . _ : / -
LOCAL_ID_RE = re.compile(r"^local:[A-Za-z0-9._:/-]{1,80}$")

MAX_STEPS = 200                      # RAM-bund: evicta vid överskott
DEFAULT_TTL_SECONDS = 600
DEFAULT_DAILY_CAP = 100
DEFAULT_NUM_CTX = 16384              # Ollamas default 4k räcker INTE — skickas explicit
MIN_NUM_CTX = 2048
MAX_NUM_CTX = 131072
MIN_TTL = 30

# steg_id -> {username, campaign_id, turn_count_at_prepare, model_id, message,
#             ctx, is_awakening, long_form, created_ts}
_steps: dict[str, dict] = {}
_steps_lock = threading.Lock()


# ── Env-flaggor (vid anropstillfället, så tester kan sätta dem per test) ──

def enabled() -> bool:
    return os.getenv("LOCAL_AI_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def ttl_seconds() -> int:
    try:
        return max(MIN_TTL, int(os.getenv("LOCAL_STEP_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv("LOCAL_DM_DAILY_CAP", str(DEFAULT_DAILY_CAP))))
    except ValueError:
        return DEFAULT_DAILY_CAP


# ── Modell-id-validering ──

def is_local_id(model_id) -> bool:
    """Strict relä-validering (sker i prepare; _validate_model_id är bara grinden)."""
    return bool(model_id) and LOCAL_ID_RE.match(str(model_id)) is not None


def ollama_model(model_id: str) -> str:
    """Strippar prefixet: 'local:qwen3:14b' → 'qwen3:14b'."""
    return str(model_id)[len(LOCAL_PREFIX):]


def clamp_num_ctx(num_ctx) -> int:
    try:
        n = int(num_ctx) if num_ctx else DEFAULT_NUM_CTX
    except (TypeError, ValueError):
        return DEFAULT_NUM_CTX
    return max(MIN_NUM_CTX, min(MAX_NUM_CTX, n))


# ── Steg-lagring (RAM, engångs, TTL, cap ~200) ──

def new_step_id() -> str:
    return secrets.token_urlsafe(24)


def _evict_locked() -> None:
    """Släng förfallna steg; vid kvarvarande överskott: äldst först."""
    now = time.time()
    ttl = ttl_seconds()
    expired = [sid for sid, s in _steps.items() if now - s.get("created_ts", 0) > ttl]
    for sid in expired:
        _steps.pop(sid, None)
    if len(_steps) >= MAX_STEPS:
        oldest = sorted(_steps.items(), key=lambda kv: kv[1].get("created_ts", 0))
        for sid, _ in oldest[: len(_steps) - MAX_STEPS + 1]:
            _steps.pop(sid, None)


def stash_step(step_id: str, data: dict) -> dict:
    with _steps_lock:
        _evict_locked()
        _steps[step_id] = data
        return data


def take_step(step_id: str) -> dict | None:
    """Engångsanvänd: poppar steget (eller None om okänt/förbrukat).

    TTL prövar anroparen mot created_ts — take släpper inte igenom steg som
    redan förfallit (de vore ändå evictade vid nästa stash)."""
    with _steps_lock:
        step = _steps.pop(step_id, None)
    if step is None:
        return None
    if time.time() - step.get("created_ts", 0) > ttl_seconds():
        return None
    return step


def clear_steps() -> None:
    """Testhjälpare: töm steg-lagret."""
    with _steps_lock:
        _steps.clear()


# ── Dygns-cap (lokala huset betalar Guardian/extraction per drag) ──

def local_dm_count_today(username: str) -> int:
    """Räkna dagens action=='local_dm'-ledgerrader (UTC-datum-prefix, samma
    mönster som _turn_ledger_bucket_breakdown's `since`)."""
    from main import _read_turn_ledger, _today_str, _TURN_LEDGER_KEEP
    today = _today_str()
    n = 0
    for rec in _read_turn_ledger(username, limit=_TURN_LEDGER_KEEP):
        if rec.get("action") == "local_dm" and str(rec.get("ts", "")).startswith(today):
            n += 1
    return n


def under_daily_cap(username: str) -> bool:
    return local_dm_count_today(username) < daily_cap()
