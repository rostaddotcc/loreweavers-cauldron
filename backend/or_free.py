"""
or_free.py — OpenRouter 🆓 Free-model integration for The Lore Weaver's Cauldron
=================================================================================

Goal: let any tier pick a small set of *experimental* DM-models served straight
from OpenRouter's free tier (no cost, cost=0), so players can compare voices
against the house models (StepFun / Qwen / DeepSeek).

Design notes (rostad, 2026-08-07):
- OpenRouter has NO public popularity/usage API. /rankings is JS-rendered and
  /api/v1/models only exposes benchmarks.elo (quality, not usage). So "top 5
  most popular" is not fetchable. Instead we keep a CURATED list of 5 free
  models (hand-picked as the best/most interesting) and ALSO fetch the live
  /api/v1/models list to (a) verify each curated id still exists + is free +
  text-only, and (b) fall back to "5 newest free text models" if curated all
  vanish.
- Reasoning models (gpt-oss, Nemotron, …) burn the whole token budget on a
  hidden `reasoning` field and return content=null UNLESS you send
  `reasoning: {"effort": "low"}` AND a real max_tokens. Verified 2026-08-07.
- The key is server-side only (never shipped to client). All players share one
  key's quota → free rate limits are LOW. This is for experimentation, not
  production load.

Model id convention in the game: "orfree:<openrouter-id>"  e.g.
"orfree:openai/gpt-oss-20b:free".  main.py routes any model_id starting with
"orfree:" into chat_free().
"""

import asyncio
import logging
import os
import time
from typing import AsyncGenerator

import httpx

logger = logging.getLogger("loreweavers.or_free")

OR_BASE_URL = "https://openrouter.ai/api/v1"
OR_FREE_KEY_ENV = "OPENROUTER_FREE_KEY"

# ── Curated "top 5" free DM-models ────────────────────────────────────────────
# Hand-picked as the most interesting free voices. Verify + refresh via the live
# /api/v1/models fetch (see _refresh()).  Change these to taste.
CURATED_FREE = [
    "openai/gpt-oss-20b:free",          # open-weights, strong reasoning
    "nvidia/nemotron-3-ultra-550b-a55b:free",  # 1M ctx, huge MoE
    "nvidia/nemotron-3-super-120b-a12b:free",  # balanced big MoE
    "poolside/laguna-s-2.1:free",       # coding-flavoured storytelling
    "cohere/north-mini-code:free",      # compact, fast
]

DISPLAY_NAMES = {
    "openai/gpt-oss-20b:free": "OpenAI gpt-oss-20b (free)",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "NVIDIA Nemotron 3 Ultra 550B (free)",
    "nvidia/nemotron-3-super-120b-a12b:free": "NVIDIA Nemotron 3 Super 120B (free)",
    "nvidia/nemotron-3-nano-30b-a3b:free": "NVIDIA Nemotron 3 Nano 30B (free)",
    "nvidia/nemotron-nano-9b-v2:free": "NVIDIA Nemotron Nano 9B (free)",
    "poolside/laguna-s-2.1:free": "Poolside Laguna S 2.1 (free)",
    "poolside/laguna-xs-2.1:free": "Poolside Laguna XS 2.1 (free)",
    "cohere/north-mini-code:free": "Cohere North Mini Code (free)",
    "inclusionai/ling-3.0-tiny:free": "inclusionAI Ling 3.0 Tiny (free)",
}

# Cache: list of verified free model dicts, refreshed periodically.
_CACHE: list[dict] = []
_CACHE_TS = 0.0
_CACHE_TTL = 3600.0  # 1h
_REASONING_MAX_TOKENS = 4000  # generous so reasoning+content both fit


def _strip_prefix(model_id: str) -> str:
    """'orfree:openai/gpt-oss-20b:free' -> 'openai/gpt-oss-20b:free'."""
    return model_id[len("orfree:"):] if model_id.startswith("orfree:") else model_id


def _key() -> str | None:
    return os.getenv(OR_FREE_KEY_ENV)


def _is_free_text(m: dict) -> bool:
    arch = m.get("architecture", {})
    inp = set(arch.get("input_modalities", []))
    out = set(arch.get("output_modalities", []))
    pr = m.get("pricing", {})
    try:
        p = float(pr.get("prompt", -1) or -1)
        c = float(pr.get("completion", -1) or -1)
    except (TypeError, ValueError):
        p = c = -1
    return (
        m.get("id", "").endswith(":free")
        and inp == {"text"}
        and out == {"text"}
        and p == 0
        and c == 0
    )


def _display(id_: str) -> str:
    if id_ in DISPLAY_NAMES:
        return DISPLAY_NAMES[id_]
    # fallback: prettify "openai/gpt-oss-20b:free" -> "OpenAI gpt-oss-20b (free)"
    prov, _, rest = id_.partition("/")
    rest = rest.replace(":free", "").strip()
    return f"{prov.title()} {rest} (free)"


async def _fetch_models() -> list[dict]:
    """Fetch /api/v1/models and return free + text-only + with reasoning support."""
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

    free = [m for m in data if _is_free_text(m)]
    # Keep only those that support the reasoning parameter (so we can force low).
    reasoning_ok = [m for m in free if "reasoning" in (m.get("supported_parameters") or [])]
    pool = reasoning_ok or free  # fall back to any free text if none support reasoning
    return pool


def _build_list(pool: list[dict]) -> list[dict]:
    """Return curated (verified) models first, else newest 5 free text models."""
    by_id = {m["id"]: m for m in pool}
    chosen: list[dict] = []
    for cid in CURATED_FREE:
        if cid in by_id:
            chosen.append(by_id[cid])
    # If curated list thinned out, top up with newest free-text models.
    if len(chosen) < 5:
        rest = sorted(
            [m for m in pool if m["id"] not in {c["id"] for c in chosen}],
            key=lambda m: m.get("created", 0),
            reverse=True,
        )
        chosen.extend(rest[: 5 - len(chosen)])
    return chosen[:5]


async def get_free_models(force: bool = False) -> list[dict]:
    """Return list of {id, display, context} for the free DM picker. Cached 1h."""
    global _CACHE, _CACHE_TS
    now = time.time()
    if not force and _CACHE and (now - _CACHE_TS) < _CACHE_TTL:
        return _CACHE
    pool = await _fetch_models()
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

    Tillåter bara kända OpenRouter-free-modeller (CURATED_FREE + DISPLAY_NAMES)
    så en spelare aldrig kan injicera godtyckliga OpenRouter-id:n.
    """
    return _strip_prefix(model_id) in DISPLAY_NAMES


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
