"""
Mörkrets Rike — LLM Model Router
=================================
Frontend skickar modell-ID → backend slår upp provider + nyckel ur .env.
API-nycklar exponeras ALDRIG till klienten.
"""

import os
from dataclasses import dataclass

@dataclass
class ModelConfig:
    model_id: str          # Frontend-värde, t.ex. "qwen3.8-max"
    display_name: str      # Visas i UI
    provider: str          # "dashscope" | "deepseek" | "mimo" | "ollama"
    api_model: str         # Faktiskt modellnamn hos providern
    base_url: str          # API-endpoint
    api_key_env: str       # Env-variabelnamn (inte själva nyckeln!)
    supports_vision: bool  # Kan analysera bilder?
    local: bool = False    # Körs lokalt?

# ═══════════════════════════════════════
# MODELLREGISTRY
# ═══════════════════════════════════════
MODELS: dict[str, ModelConfig] = {
    # ── Qwen (DashScope) ──
    "qwen3.8-max": ModelConfig(
        model_id="qwen3.8-max",
        display_name="Qwen 3.8 Max",
        provider="dashscope",
        api_model="qwen3.8-max-preview",
        base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key_env="DASHSCOPE_API_KEY",
        supports_vision=True,
    ),
    "qwen3.7-plus": ModelConfig(
        model_id="qwen3.7-plus",
        display_name="Qwen 3.7 Plus",
        provider="dashscope",
        api_model="qwen3.7-plus",
        base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key_env="DASHSCOPE_API_KEY",
        supports_vision=True,
    ),

    # ── DeepSeek ──
    "deepseek-v4-pro": ModelConfig(
        model_id="deepseek-v4-pro",
        display_name="DeepSeek V4 Pro",
        provider="deepseek",
        api_model="deepseek-v4-pro",
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key_env="DEEPSEEK_API_KEY",
        supports_vision=False,
    ),
    "deepseek-v4-flash": ModelConfig(
        model_id="deepseek-v4-flash",
        display_name="DeepSeek V4 Flash",
        provider="deepseek",
        api_model="deepseek-v4-flash",
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key_env="DEEPSEEK_API_KEY",
        supports_vision=False,
    ),

    # ── MiMo (Xiaomi) ──
    "mimo-v2": ModelConfig(
        model_id="mimo-v2",
        display_name="MiMo V2",
        provider="mimo",
        api_model="mimo-v2",
        base_url=os.getenv("MIMO_BASE_URL", "https://api.mimo.xiaomi.com/v1"),
        api_key_env="MIMO_API_KEY",
        supports_vision=True,
    ),

    # ── Ollama (lokalt, ingen nyckel) ──
    "ollama:qwen3:8b": ModelConfig(
        model_id="ollama:qwen3:8b",
        display_name="Qwen3 8B (lokal)",
        provider="ollama",
        api_model="qwen3:8b",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key_env="",  # Ingen nyckel behövs
        supports_vision=False,
        local=True,
    ),
    "ollama:deepseek-r1:7b": ModelConfig(
        model_id="ollama:deepseek-r1:7b",
        display_name="DeepSeek R1 7B (lokal)",
        provider="ollama",
        api_model="deepseek-r1:7b",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key_env="",
        supports_vision=False,
        local=True,
    ),
}


def get_model(model_id: str) -> ModelConfig:
    """Hämta modellkonfig. Frontend skickar model_id, aldrig nycklar."""
    if model_id not in MODELS:
        raise ValueError(f"Okänd modell: {model_id}")
    return MODELS[model_id]


def get_api_key(config: ModelConfig) -> str | None:
    """Läs API-nyckel ur environment. Returnerar None för lokala modeller."""
    if not config.api_key_env:
        return None
    key = os.getenv(config.api_key_env)
    if not key:
        raise RuntimeError(
            f"API-nyckel saknas: sätt {config.api_key_env} i backend/.env"
        )
    return key


def list_models_for_frontend() -> list[dict]:
    """
    Returnera modellista för frontend — UTAN nycklar, base_urls, eller interna namn.
    Bara det spelaren behöver se.
    """
    return [
        {
            "id": m.model_id,
            "name": m.display_name,
            "provider": m.provider,
            "vision": m.supports_vision,
            "local": m.local,
        }
        for m in MODELS.values()
    ]


# ═══════════════════════════════════════
# DM SYSTEM PROMPT (injectas med vald modell)
# ═══════════════════════════════════════
DM_SYSTEM_PROMPT = """Du är Dungeon Master i "Mörkrets Rike", ett mörkt fantasy-D&D-äventyr.

## Dina roller
- **Narratör**: Beskriv miljöer, stämningar, konsekvenser. Var stämningsfull, inte verbos.
- **NPC-skådespelare**: När du talar som en NPC, inled med deras namn. Varje NPC har egen personlighet.
- **Regeldomare**: Begär tärningskast när det passar. Tolka resultat narrativt.
- **Världsbyggare**: Bygg världen tillsammans med spelaren. Kom ihåg detaljer.

## Regler
- Svara på svenska om spelaren skriver på svenska.
- Håll svar under 150 ord för narration, kortare för NPC-dialog.
- Begär kast med formatet: [KAST: 1d20+4 SMIDIGHET för att smyga]
- Avsluta alltid med en öppning — vad kan spelaren göra?
- Var INTE rädd för att säga nej. Konsekvenser ska kännas.

## Ton
Mörk, atmosfärisk, lite hotfull men aldrig hopplös. Tänk Dark Souls möter Sagan om Ringen.
"""
