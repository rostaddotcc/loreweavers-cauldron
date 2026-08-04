"""
The Lore Weaver's Cauldron — RAG-modul (Retrieval-Augmented Generation)
=============================================================

Arkitektur
----------
Den här modulen kopplar samman två externa tjänster:

  • **Ollama** (nomic-embed-text) — genererar 768-dimensionella vektorer
    via HTTP-API:et ``POST {OLLAMA_URL}/api/embed`` (den moderna endpointen;
    ``/api/embeddings`` ignorerar num_ctx och kraschar på långa sessioner).
  • **Qdrant** — vektordatabas som lagrar semantiska index i samlingen
    ``loreweavers_cauldron`` (768-dim, Cosine-likhet).

Flöde
-----
1. **Indexering**: Text (transkript, lore, fakta, sammanfattningar)
   chunkas → embeddas via Ollama → lagras som punkter i Qdrant med
   deterministiska UUID:n (innehållshash) så att om-indexering inte
   skapar dubbletter.
2. **Hämtning (retrieval)**: En fråga embeddas → Qdrant-sökning med
   payload-filter på användarnamn → topp-k träffar returneras.
3. **Transkript-chunkning**: Hela transkript delas i överlappande
   block om ~500 tecken med bevarade turgränser.

Användning
----------
    from rag import index_transcript, retrieve, index_lore, qdrant_healthy

Alla funktioner är asynkrona (async/await).
Miljövariabler: QDRANT_URL, OLLAMA_URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Batch,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

logger = logging.getLogger("loreweavers.rag")

# ── Konfiguration ──────────────────────────────────────────────────
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
COLLECTION: str = "loreweavers_cauldron"
EMBED_MODEL: str = "nomic-embed-text"
EMBED_DIM: int = 768

# Chunkning
CHUNK_SIZE: int = 500        # Målstorlek i tecken
CHUNK_OVERLAP: int = 100     # Överlapp mellan chunks

# Retry-inställningar för Ollama-anrop
MAX_RETRIES: int = 3
RETRY_DELAY: float = 1.0     # Sekunder, fördubblas vid varje försök

# Batch-storlek för Qdrant-upsert
BATCH_SIZE: int = 64

# Deterministisk UUID-rymd (fix namespace för projektet)
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL-rymd


# ── Hjälpfunktioner ────────────────────────────────────────────────

def _now_iso() -> str:
    """Aktuell UTC-tid som ISO-8601-sträng."""
    return datetime.now(timezone.utc).isoformat()


def _content_id(text: str, username: str, campaign_id: str) -> str:
    """
    Deterministiskt UUID baserat på innehåll + ägare.
    Samma text → samma ID → ingen dubblett vid om-indexering.
    """
    raw = f"{username}:{campaign_id}:{text}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return str(uuid.uuid5(_NAMESPACE, digest))


def _qdrant_client() -> AsyncQdrantClient:
    """Skapa en ny asynkron Qdrant-klient."""
    return AsyncQdrantClient(url=QDRANT_URL, timeout=30)


# ── 1. Embedding via Ollama ───────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    """
    Generera en 768-dim vektor för *text* via Ollama nomic-embed-text.

    Använder den moderna ``/api/embed``-endpointen (sedan Ollama 0.3x) —
    den gamla ``/api/embeddings`` ignorerar num_ctx/num_batch och laddar
    alltid n_ctx_slot=2048, vilket kraschar på längre sessioner
    ("input is too large … increase the physical batch size").

    Retry-logik: upp till MAX_RETRIES försök med exponentiell backoff.
    Kastar RuntimeError om alla försök misslyckas.
    """
    url = f"{OLLAMA_URL}/api/embed"
    payload = {"model": EMBED_MODEL, "input": text}
    delay = RETRY_DELAY

    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                embedding = data["embeddings"][0]
                if len(embedding) != EMBED_DIM:
                    raise ValueError(
                        f"Förväntade {EMBED_DIM} dim, fick {len(embedding)}"
                    )
                return embedding
            except Exception as exc:
                logger.warning(
                    "Embedding-försök %d/%d misslyckades: %s",
                    attempt, MAX_RETRIES, exc,
                )
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"Kunde inte generera embedding efter {MAX_RETRIES} försök"
                    ) from exc
                await asyncio.sleep(delay)
                delay *= 2

    # Nåbar men aldrig (raise ovan) — behövs för typkontroll
    raise RuntimeError("Oväntat: embedding-loopen avslutades utan resultat")


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embedda flera texter sekventiellt (Ollama saknar batch-API)."""
    return [await embed_text(t) for t in texts]


# ── 2. Indexering till Qdrant ─────────────────────────────────────

async def index_chunks(
    chunks: list[dict[str, Any]],
    username: str,
    campaign_id: str,
) -> int:
    """
    Indexera en lista med text-chunks i Qdrant.

    Varje chunk-dict ska ha:
        text       – str (obligatoriskt)
        chunk_type – 'transcript' | 'lore' | 'fact' | 'summary'
        turn       – int (valfritt, default 0)

    Returnerar antalet indexerade punkter.
    """
    if not chunks:
        return 0

    client = _qdrant_client()
    indexed = 0

    try:
        # Bearbeta i batchar
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            texts = [c["text"] for c in batch]

            # Generera embeddings för hela batchen
            vectors = await embed_batch(texts)

            # Bygg Qdrant-punkter
            points: list[PointStruct] = []
            for chunk, vector in zip(batch, vectors):
                text = chunk["text"]
                point_id = _content_id(text, username, campaign_id)
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "username": username,
                            "campaign_id": campaign_id,
                            "text": text,
                            "chunk_type": chunk.get("chunk_type", "transcript"),
                            "turn": chunk.get("turn", 0),
                            "timestamp": _now_iso(),
                        },
                    )
                )

            # Batch-upsert (vänta på bekräftelse)
            await client.upsert(
                collection_name=COLLECTION,
                points=points,
                wait=True,
            )
            indexed += len(points)
            logger.info(
                "Indexerade batch %d–%d (%d punkter) för %s/%s",
                i, i + len(batch), len(points), username, campaign_id,
            )
    finally:
        await client.close()

    return indexed


# ── 3. Hämtning (retrieval) ───────────────────────────────────────

async def retrieve(
    query: str,
    username: str,
    top_k: int = 5,
    campaign_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Hämta topp-*top_k* relevanta chunks för en fråga.

    Filtrerar på username (och valfritt campaign_id) via Qdrant payload-filter.
    Returnerar lista med dicts: {text, score, chunk_type, turn}.
    """
    query_vector = await embed_text(query)

    # Bygg filter: alltid username, eventuellt campaign_id
    conditions = [
        FieldCondition(key="username", match=MatchValue(value=username)),
    ]
    if campaign_id:
        conditions.append(
            FieldCondition(key="campaign_id", match=MatchValue(value=campaign_id)),
        )
    query_filter = Filter(must=conditions)

    client = _qdrant_client()
    try:
        result = await client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
    finally:
        await client.close()

    # Formatera resultat
    hits: list[dict[str, Any]] = []
    for point in result.points:
        payload = point.payload or {}
        hits.append(
            {
                "text": payload.get("text", ""),
                "score": point.score,
                "chunk_type": payload.get("chunk_type", ""),
                "turn": payload.get("turn", 0),
            }
        )
    return hits


# ── 4. Transkript-chunkning ───────────────────────────────────────

def chunk_transcript(
    messages: list[dict[str, Any]],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """
    Dela ett transkript i överlappande chunks om ~*chunk_size* tecken.

    Parametrar:
        messages – lista med {role, content, turn}
        chunk_size – målstorlek per chunk
        overlap – antal tecken överlapp mellan chunks

    Turgränser bevaras: en chunk bryts aldrig mitt i ett meddelande.
    Varje chunk får chunk_type='transcript' och högsta turn-nummer.
    """
    if not messages:
        return []

    chunks: list[dict[str, Any]] = []
    current_text = ""
    current_turns: list[int] = []

    for msg in messages:
        role = msg.get("role", "okänd")
        content = msg.get("content", "")
        turn = msg.get("turn", 0)

        # Formatera meddelandet som läsbar text
        line = f"[{role.upper()}] {content}"

        # Om nuvarande buffer + ny rad överskrider gränsen → spara chunk
        if current_text and len(current_text) + len(line) + 1 > chunk_size:
            chunks.append(
                {
                    "text": current_text.strip(),
                    "chunk_type": "transcript",
                    "turn": max(current_turns) if current_turns else 0,
                }
            )
            # Behåll överlapp: ta de sista `overlap` tecknen
            if overlap > 0 and len(current_text) > overlap:
                current_text = current_text[-overlap:] + "\n" + line
            else:
                current_text = line
            current_turns = [turn]
        else:
            if current_text:
                current_text += "\n" + line
            else:
                current_text = line
            current_turns.append(turn)

    # Sista chunken
    if current_text.strip():
        chunks.append(
            {
                "text": current_text.strip(),
                "chunk_type": "transcript",
                "turn": max(current_turns) if current_turns else 0,
            }
        )

    return chunks


async def index_transcript(
    messages: list[dict[str, Any]],
    username: str,
    campaign_id: str,
) -> int:
    """
    Chunka ett helt transkript och indexera alla chunks i Qdrant.

    Parametrar:
        messages – lista med {role, content, turn}
        username – ägarens användarnamn
        campaign_id – kampanjens ID

    Returnerar antalet indexerade chunks.
    """
    chunks = chunk_transcript(messages)
    if not chunks:
        logger.info("Tomt transkript — inget att indexera.")
        return 0
    return await index_chunks(chunks, username, campaign_id)


# ── 5. Lore-indexering ────────────────────────────────────────────

async def index_lore(
    title: str,
    text: str,
    username: str,
    campaign_id: str,
) -> int:
    """
    Indexera en lore-post (titel + text) som en enda chunk.

    Returnerar 1 om indexerad, 0 om texten var tom.
    """
    combined = f"{title}\n\n{text}" if title else text
    if not combined.strip():
        return 0

    chunk = {
        "text": combined.strip(),
        "chunk_type": "lore",
        "turn": 0,
    }
    return await index_chunks([chunk], username, campaign_id)


# ── 6. Hälsokontroll ──────────────────────────────────────────────

async def purge_user(username: str) -> int:
    """
    Radera alla vektorer för en användare ur Qdrant.
    Anropas när en användares kampanjer raderas, så att inget
    långtidsminne läcker kvar. Returnerar antalet raderade punkter.
    """
    try:
        client = _qdrant_client()
        # Räkna först (för loggning) — scrolla utan vektorer
        points, _next = await client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="username", match=MatchValue(value=username)),
            ]),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        # delete() tar bort allt som matchar filtret
        await client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(filter=Filter(must=[
                FieldCondition(key="username", match=MatchValue(value=username)),
            ])),
        )
        await client.close()
        logger.info("Cleared Qdrant vectors for %s", username)
        return len(points)
    except Exception as exc:
        logger.warning("Qdrant cleanup failed for %s: %s", username, exc)
        return 0


async def qdrant_healthy() -> bool:
    """
    Kontrollera att Qdrant är nåbar och svarar.

    Returnerar True om tjänsten är frisk, False annars.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{QDRANT_URL}/healthz")
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Qdrant health check failed: %s", exc)
        return False


async def ollama_healthy() -> bool:
    """
    Kontrollera att Ollama är nåbar och har nomic-embed-text tillgänglig.

    Returnerar True om modellen finns, False annars.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            return any(EMBED_MODEL in m.get("name", "") for m in models)
    except Exception as exc:
        logger.warning("Ollama health check failed: %s", exc)
        return False
