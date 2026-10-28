"""
or_free.py — OpenRouter 🆓 Free-model integration for The Lore Weaver's Cauldron
=================================================================================

Goal: let any tier pick a small set of *experimental* DM-models served straight
from OpenRouter's free tier (no cost, cost=0), so players can compare voices
against the house models (StepFun / Qwen / DeepSeek).

Design notes (rostad, 2026-08-07, reviderat 2026-10-22):
- OpenRouter has NO public popularity/usage API. /rankings is JS-rendered and
  /api/v1/models only exposes benchmarks.elo (quality, not usage). So "most
  popular" is not fetchable. Instead we keep a CURATED list of hand-picked
  free models (best/most interesting), pin them first, and fill the rest of
  the picker with the live /api/v1/models list newest-first.
- 2026-10-22 (rostad): the picker is NOT capped at 5 any more, and a model no
  longer has to be text-ONLY. Anything that accepts TEXT (plus optional
  image/audio/video input) and answers in text, for $0, shows up. The game
  only ever sends text, so extra input modalities are harmless.
- Reasoning models (gpt-oss, Nemotron, …) burn the whole token budget on a
  hidden `reasoning` field and return content=null UNLESS you send
  `reasoning: {"effort": "low"}` AND a real max_tokens. Verified 2026-08-07.
- The key is server-side only (never shipped to client). All players share one
  key's quota → free rate limits are LOW. This is for experimentation, not
  production load.

Model id convention in the game: "orfree:<openrouter-id>"  e.g.
"orfree:minimax/minimax-m3.1-flash:free".  main.py routes any model_id starting
with "orfree:" into chat_free().
"""

import logging
import os
import time
from typing import AsyncGenerator

import httpx

logger = logging.getLogger("loreweavers.or_free")

OR_BASE_URL = "https://openrouter.ai/api/v1"
OR_FREE_KEY_ENV = "OPENROUTER_FREE_KEY"

# ── Curated free DM-models (pinnade först i väljaren) ─────────────────────────
# Hand-picked as the most interesting free voices; pinned ahead of the rotating
# newest-first fill. Verify + refresh via the live /api/v1/models fetch.
# 2026-10-22: openai/gpt-oss-20b:free bortplockad (inte längre $0 på OpenRouter)
# och nvidia/nemotron-3-super-120b-a12b:free bortplockad (404 "Provider returned
# error" 3/3 prober) — minimax/minimax-m3.1-flash + recursive/flint in i stället.
CURATED_FREE = [
    "minimax/minimax-m3.1-flash:free",        # 1M ctx, text+bild+video in
    "nvidia/nemotron-3.5-lightning:free",     # 1M ctx, snabb
    "nvidia/nemotron-3-ultra-550b-a55b:free",  # 1M ctx, stor MoE
    "poolside/laguna-s-2.1:free",             # kodsmakad berättarröst
    "recursive/flint-v1.0:free",              # nyast 2026-10-22
]

# Alla gratis modeller som kan agera DM (text in — fler modaliteter ok — text ut).
DISPLAY_NAMES = {
    "minimax/minimax-m3.1-flash:free": "MiniMax M3.1 Flash (free)",
    "recursive/flint-v1.0:free": "Recursive Flint v1.0 (free)",
    "xingchen-agi/xing4.0-29b-a4b:free": "XingChen Xing4.0 29B A4B (free)",
    "nvidia/nemotron-3.5-lightning:free": "NVIDIA Nemotron 3.5 Lightning (free)",
    "nvidia/nemotron-3.5-super-vl:free": "NVIDIA Nemotron 3.5 Super VL (free)",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "NVIDIA Nemotron 3 Ultra 550B (free)",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": "NVIDIA Nemotron 3 Nano Omni 30B (free)",
    "dots-studio/dots-3-note-preview:free": "Dots Studio Dots3-Note (free)",
    "liquid/lfm-2.5-2.6b:free": "Liquid LFM2.5 2.6B (free)",
    "poolside/laguna-s-2.1:free": "Poolside Laguna S 2.1 (free)",
    "poolside/laguna-xs-2.1:free": "Poolside Laguna XS 2.1 (free)",
    "cohere/north-mini-code:free": "Cohere North Mini Code (free)",
    "google/gemma-4-26b-a4b-it:free": "Google Gemma 4 26B A4B (free)",
    "google/gemma-4-31b-it:free": "Google Gemma 4 31B (free)",
}

# Allow-list-bas: curated + alla kända visningsnamn. Fylls PÅ med hela den
# live-verifierade poolen i get_free_models() (se _KNOWN) — annars skulle en
# modell som bara kom in via "nyaste fria"-påfyllningen synas i väljaren men
# tyst klampas till default när spelaren valde den (main._clamp_player_model).
_STATIC_KNOWN: set[str] = set(CURATED_FREE) | set(DISPLAY_NAMES)
_KNOWN: set[str] = set()

# Cache: list of verified free model dicts, refreshed periodically.
_CACHE: list[dict] = []
_CACHE_TS = 0.0
_CACHE_TTL = 3600.0  # 1h
_REASONING_MAX_TOKENS = 4000  # generous so reasoning+content both fit
_MAX_FREE_MODELS = 20  # säkerhetsräls, inte ett designmål — allt under visas
# Verktygs-/modereringsmodeller som råkar vara gratis + text-in/text-ut.
_NON_CHAT_ID_PARTS = ("content-safety", "moderation", "guardrail")
# Gratis modeller som listas av OpenRouter men inte går att anropa (prober
# 2026-10-22). De visas inte i väljaren — en död rad i dropdownen ger spelaren
# ett fel mitt i spelet. Ta bort posten när/om OpenRouter öppnar modellen igen.
#   404 = "Provider returned error" (provider borta) · 403 = "only available on
#   agentic harnesses" (tillåter bara OpenRouter:s egen agent-väg, ej rå API).
# OBS: tillfälliga 429 (delad nyckelkvot) blockerar vi INTE — de syns medvetet,
# fria modeller delar en kvot och kan vara långsamma/rate-limiterade.
_BLOCKED_IDS = {
    "nvidia/nemotron-3-super-120b-a12b:free": "404 Provider returned error (2026-10-22)",
    "thinkingmachines/inkling:free": "403 agentic-harness only (2026-10-22)",
    "thinkingmachines/inkling-small:free": "403 agentic-harness only (2026-10-22)",
}


def _strip_prefix(model_id: str) -> str:
    """'orfree:openai/gpt-oss-20b:free' -> 'openai/gpt-oss-20b:free'."""
    return model_id[len("orfree:"):] if model_id.startswith("orfree:") else model_id


def _key() -> str | None:
    return os.getenv(OR_FREE_KEY_ENV)


def _is_free_chat(m: dict) -> bool:
    """Gratis DM-modell: TEXT in (fler modaliteter tillåtna) och TEXT ut.

    2026-10-22 (rostad): tidigare krävdes `inp == {"text"}` — det filtrerade
    bort modeller som tar text OCH t.ex. bild/video (minimax/minimax-m3.1-flash)
    innan listan ens byggdes, trots att de fungerar som DM (spelet skickar bara
    text). output_modalities måste fortfarande vara EXAKT {"text"} — en TTS-
    eller bildmodell kan inte svara i chatten. Verktygs-/modereringsmodeller
    (content-safety m.fl.) filtreras på id.
    """
    arch = m.get("architecture", {})
    inp = set(arch.get("input_modalities", []))
    out = set(arch.get("output_modalities", []))
    mid = m.get("id", "")
    pr = m.get("pricing", {})
    try:
        p = float(pr.get("prompt", -1) or -1)
        c = float(pr.get("completion", -1) or -1)
    except (TypeError, ValueError):
        p = c = -1
    return (
        mid.endswith(":free")
        and "text" in inp
        and out == {"text"}
        and p == 0
        and c == 0
        and not any(part in mid for part in _NON_CHAT_ID_PARTS)
    )


def _display(id_: str) -> str:
    if id_ in DISPLAY_NAMES:
        return DISPLAY_NAMES[id_]
    # fallback: prettify "openai/gpt-oss-20b:free" -> "OpenAI gpt-oss-20b (free)"
    prov, _, rest = id_.partition("/")
    rest = rest.replace(":free", "").strip()
    return f"{prov.title()} {rest} (free)"


async def _fetch_models() -> list[dict]:
    """Fetch /api/v1/models and return free DM models (text in, text out, $0)."""
    key = _key()
    if not key:
        logger.warning("🆓 OPENROUTER_FREE_KEY not set — free models unavailable")
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{OR_BASE_URL}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception as e:
        logger.error("🆓 Failed to fetch OpenRouter models: %s", e)
        return []

    free = [m for m in data if _is_free_chat(m) and m["id"] not in _BLOCKED_IDS]
    if any(m["id"] in _BLOCKED_IDS for m in data if _is_free_chat(m)):
        logger.info("🆓 %d free model(s) hidden (known 404 upstream): %s",
                    sum(1 for m in data if _is_free_chat(m) and m["id"] in _BLOCKED_IDS),
                    ", ".join(_BLOCKED_IDS))
    # Keep only those that support the reasoning parameter (so we can force low).
    reasoning_ok = [m for m in free if "reasoning" in (m.get("supported_parameters") or [])]
    pool = reasoning_ok or free  # fall back to any free text if none support reasoning
    return pool


def _build_list(pool: list[dict]) -> list[dict]:
    """Curated (handplockade) först, sedan resten av poolen nyast-först.

    2026-10-22 (rostad): inget 5-tak längre — varje gratis modell som kan svara
    i text ska synas i väljaren, inte bara de fem första. _MAX_FREE_MODELS är
    bara en säkerhetsräls mot en orimligt lång dropdown.
    """
    by_id = {m["id"]: m for m in pool}
    chosen: list[dict] = [by_id[cid] for cid in CURATED_FREE if cid in by_id]
    rest = sorted(
        [m for m in pool if m["id"] not in {c["id"] for c in chosen}],
        key=lambda m: m.get("created", 0),
        reverse=True,
    )
    return (chosen + rest)[:_MAX_FREE_MODELS]


async def get_free_models(force: bool = False) -> list[dict]:
    """Return list of {id, display, context} for the free DM picker. Cached 1h."""
    global _CACHE, _CACHE_TS
    now = time.time()
    if not force and _CACHE and (now - _CACHE_TS) < _CACHE_TTL:
        return _CACHE
    pool = await _fetch_models()
    if pool:
        # Allow-listen = exakt det vi faktiskt visar. Utan detta klampas en
        # påfylld modell (som recursive/flint) tyst till default när en spelare
        # väljer den, eftersom is_known_free bara kände curated + DISPLAY_NAMES.
        _KNOWN.clear()
        _KNOWN.update(m["id"] for m in pool)
    chosen = _build_list(pool)
    _CACHE = [
        {
            "id": f"orfree:{m['id']}",
            "display": _display(m["id"]),
            "context": m.get("context_length"),
            "provider": "openrouter-free",
        }
        for m in chosen
    ]
    _CACHE_TS = now
    logger.info("🆓 Free OpenRouter models refreshed: %d", len(_CACHE))
    return _CACHE


def is_known_free(model_id: str) -> bool:
    """Sync allow-list för 'orfree:'-id:n (används av main.py clamping/validering).

    Tillåter curated/DISPLAY_NAMES PLUS allt som finns i den senast hämtade
    live-poolen (_KNOWN), så en påfylld modell som recursive/flint faktiskt går
    att spela med. Godtyckliga OpenRouter-id:n (t.ex. orfree:evil/not-real:free)
    avvisas fortfarande — de finns inte i någon av mängderna.
    """
    or_id = _strip_prefix(model_id)
    return or_id in _KNOWN or or_id in _STATIC_KNOWN


def known_free_count() -> int:
    """Antal id:n i allow-listen (diagnostik/loggning)."""
    return len(_KNOWN | _STATIC_KNOWN)


async def warm_free_models() -> None:
    """Förvärm cache + allow-list vid uppstart (main._lifespan).

    Sväljer alla fel — ett nätavbrott mot OpenRouter får aldrig stoppa starten;
    då gäller den statiska allow-listen (curated + DISPLAY_NAMES) tills nästa
    lyckade hämtning.
    """
    try:
        models = await get_free_models(force=True)
        logger.info("🆓 free-model warmup: %d modeller, %d kända id:n",
                    len(models), known_free_count())
    except Exception as e:  # pragma: no cover — nätberoende
        logger.warning("🆓 free-model warmup failed: %s", e)


async def chat_free(
    model_id: str,
    messages: list[dict],
    max_tokens: int = _REASONING_MAX_TOKENS,
    temperature: float = 0.8,
    timeout: float = 180,
) -> tuple[str, str, dict]:
    """
    Call an OpenRouter free model. Returns (content, reasoning, usage) to match
    main._call_llm_with_reasoning's signature.

    Forces `reasoning: {"effort": "low"}` so reasoning models don't eat the
    whole budget and return empty content.
    """
    key = _key()
    if not key:
        raise RuntimeError("OPENROUTER_FREE_KEY not configured")
    or_id = _strip_prefix(model_id)
    body = {
        "model": or_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning": {"effort": "low"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    t0 = time.time()
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{OR_BASE_URL}/chat/completions", headers=headers, json=body
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenRouter free error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or ""
    usage = data.get("usage", {}) or {}
    elapsed = round(time.time() - t0, 1)
    logger.info(
        "🆓 free DM %s → %d content / %d reasoning chars (%.1fs, cost=%s)",
        or_id, len(content), len(reasoning), elapsed, usage.get("cost"),
    )
    return content, reasoning, {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


async def chat_free_stream(
    model_id: str,
    messages: list[dict],
    max_tokens: int = _REASONING_MAX_TOKENS,
    temperature: float = 0.8,
    timeout: float = 300,
) -> AsyncGenerator[tuple[str, str, dict | None], None]:
    """Strömmande variant av chat_free — för karaktärsskapande (SSE).

    Yieldar (reasoning_delta, content_delta, usage_or_none) allt eftersom
    OpenRouter genererar — samma kontrakt som main._stream_llm. Sista yielden
    bär usage (tokens) om providern rapporterade det
    (stream_options.include_usage). Reasoning-modeller får
    `reasoning: {"effort": "low"}` tvingat (annars bränner de budgeten på
    dolt tänkande och returnerar tom content — se chat_free).
    """
    import json

    key = _key()
    if not key:
        raise RuntimeError("OPENROUTER_FREE_KEY not configured")
    or_id = _strip_prefix(model_id)
    body = {
        "model": or_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "reasoning": {"effort": "low"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    t0 = time.time()
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", f"{OR_BASE_URL}/chat/completions", headers=headers, json=body
        ) as resp:
            if resp.status_code != 200:
                err_body = (await resp.aread()).decode(errors="replace")
                raise RuntimeError(
                    f"OpenRouter free error {resp.status_code}: {err_body[:300]}"
                )
            usage: dict | None = None
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    d = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if d.get("usage"):
                    usage = d["usage"]
                ch = (d.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                r = delta.get("reasoning") or delta.get("reasoning_content") or ""
                c = delta.get("content") or ""
                if r or c:
                    yield r, c, None
    elapsed = round(time.time() - t0, 1)
    logger.info(
        "🆓 free stream %s → done (%.1fs, usage=%s)",
        or_id, elapsed, bool(usage),
    )
    yield "", "", usage
