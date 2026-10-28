"""
selfhost.py — self-host build mode for The Lore Weaver's Cauldron
=================================================================

SELFHOST=1 turns the game into a single-user, fully local install: no billing,
no turn quota, and only models that live on the operator's own Ollama server.
main.py owns the billing/quota side of that switch; this module owns the
Ollama-facing side:

- discovery  : ask Ollama's native /api/tags which models are installed
- plumbing   : turn a bare Ollama model name into the game's "ollama:<name>" id
               and back again

Model id convention in the game: "ollama:<name>"  e.g. "ollama:qwen3:8b".
Chat calls go through Ollama's OpenAI-compatible endpoint, so the base_url used
by models.ModelConfig ends in "/v1" while discovery uses the native "/api/tags"
(hence ollama_base() deliberately does NOT append /v1).

Ollama needs no API key — models.ollama_config() therefore sets api_key_env=""
and models.get_api_key() returns None, which makes main.py omit the
Authorization header. Keep it that way.

Cache: discovery is cached for 60 s (llama.cpp cold starts and the tags call are
cheap, but the picker and every turn ask for the roster). A failed discovery is
cached for only 5 s so a freshly started Ollama shows up quickly.
"""

import logging
import os
import threading
import time

import httpx

logger = logging.getLogger("loreweavers.selfhost")

PREFIX = "ollama:"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

_TRUTHY = {"1", "true", "yes", "on"}

# Model families that are never chat models (embeddings / rerankers).
# Used as a second filter in case an older Ollama build omits "capabilities".
_NON_CHAT_FAMILIES = {"nomic-bert", "bert", "bge", "e5"}

_CACHE_TTL = 60.0   # how long a successful discovery is trusted
_FAIL_TTL = 5.0     # how long an empty/failed discovery is trusted

_CACHE: list[str] | None = None   # None = never fetched
_CACHE_TS = 0.0
_LOCK = threading.Lock()


def enabled() -> bool:
    """True when SELFHOST is one of 1/true/yes/on (read at call time).

    Read per call so tests (and a restarted container) can flip it without
    reimporting the module.
    """
    return os.getenv("SELFHOST", "").strip().lower() in _TRUTHY


def ollama_base() -> str:
    """Ollama root URL (no /v1 — that is only for the OpenAI-compatible path)."""
    return os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).strip().rstrip("/")


def _fetch_tags(timeout: float = 4.0) -> list[dict]:
    """GET {ollama_base()}/api/tags → the raw "models" list.

    Raises on HTTP or parse errors on purpose: callers (discover_models) decide
    what a failure means, and a silent [] here would hide a broken server.
    """
    url = f"{ollama_base()}/api/tags"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    models = data.get("models")
    if not isinstance(models, list):
        raise ValueError(f"Ollama /api/tags returned no model list: {str(data)[:200]}")
    return models


def _is_chat_model(m: dict) -> bool:
    """Skip embedding-only models and non-chat families.

    Newer Ollama reports capabilities ("completion", "vision", "embedding").
    Rule: if "embedding" is there and "completion" is not, it cannot chat.
    Older builds have no capabilities at all, so fall back to details.family.
    """
    caps = m.get("capabilities")
    if isinstance(caps, list):
        caps_l = [str(c).lower() for c in caps]
        if "embedding" in caps_l and "completion" not in caps_l:
            return False
    family = str((m.get("details") or {}).get("family", "")).lower()
    if family in _NON_CHAT_FAMILIES:
        return False
    return True


def discover_models(timeout: float = 4.0) -> list[str]:
    """Names of chat-capable models installed on the local Ollama server.

    Sorted alphabetically, cached 60 s (success) / 5 s (failure).
    Never raises — an unreachable Ollama means "no local models", and the caller
    (roster/default_model_id) degrades to an empty picker.
    """
    global _CACHE, _CACHE_TS

    now = time.monotonic()
    with _LOCK:
        if _CACHE is not None:
            ttl = _CACHE_TTL if _CACHE else _FAIL_TTL
            if (now - _CACHE_TS) < ttl:
                return list(_CACHE)

    try:
        tags = _fetch_tags(timeout=timeout)
        names = sorted(
            {
                str(m.get("name") or m.get("model") or "").strip()
                for m in tags
                if isinstance(m, dict) and _is_chat_model(m)
            }
            - {""}
        )
    except Exception as e:
        logger.warning("🖥️ selfhost: Ollama discovery failed (%s) — no local models", e)
        with _LOCK:
            _CACHE, _CACHE_TS = [], time.monotonic()
        return []

    with _LOCK:
        _CACHE, _CACHE_TS = names, time.monotonic()
    logger.info("🖥️ selfhost: %d local chat model(s): %s", len(names), ", ".join(names) or "-")
    return list(names)


def default_model_id() -> str:
    """SELFHOST_MODEL if set, else the first discovered local model, else ""."""
    override = os.getenv("SELFHOST_MODEL", "").strip()
    if override:
        return model_id(override)
    names = discover_models()
    return model_id(names[0]) if names else ""


def model_id(name: str) -> str:
    """"qwen3:8b" → "ollama:qwen3:8b" (idempotent for already-prefixed ids)."""
    n = (name or "").strip()
    if n.startswith(PREFIX):
        n = n[len(PREFIX):].strip()
    return f"{PREFIX}{n}" if n else ""


def is_ollama_id(model_id: str) -> bool:
    """True for ids routed to the local Ollama server."""
    return (model_id or "").startswith(PREFIX)


def resolve(model_id: str) -> str:
    """"ollama:qwen3:8b" → "qwen3:8b". Raises ValueError for anything else."""
    mid = (model_id or "").strip()
    if not mid.startswith(PREFIX):
        raise ValueError(f"Inte ett ollama-id: {model_id!r}")
    name = mid[len(PREFIX):].strip()
    if not name:
        raise ValueError(f"Ollama-id utan modellnamn: {model_id!r}")
    return name


def roster() -> list[dict]:
    """Picker entries for the local models — same shape as list_models_for_frontend()."""
    return [
        {"id": f"{PREFIX}{name}", "name": f"{name} (local)", "provider": "ollama", "vision": True}
        for name in discover_models()
    ]


def invalidate_cache() -> None:
    """Drop the discovery cache (tests, and settings changes to OLLAMA_URL)."""
    global _CACHE, _CACHE_TS
    with _LOCK:
        _CACHE, _CACHE_TS = None, 0.0