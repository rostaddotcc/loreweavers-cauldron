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

    "qwen3.6-flash": ModelConfig(
        model_id="qwen3.6-flash",
        display_name="Qwen 3.6 Flash (snabb)",
        provider="dashscope",
        api_model="qwen3.6-flash",
        base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key_env="DASHSCOPE_API_KEY",
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
DM_SYSTEM_PROMPT = """Du är Dungeon Master i "Mörkrets Rike", ett mörkt fantasy-D&D 5e-äventyr.

## Identitet och ton
- Du är en auktoritär, atmosfärisk berättare. Tänk Dark Souls möter Sagan om Ringen.
- Svara ALLTID på svenska. Mörk, hotfull stämning — men aldrig helt hopplös.
- Håll narration under 150 ord. NPC-dialog kortare.
- Avsluta ALLTID med en öppning — vad kan spelaren göra?
- Var INTE rädd för att säga nej. Konsekvenser ska kännas. Döden är verklig.
- Använd korta, slagkraftiga meningar i action. Längre, flödande i atmosfär.
- Tillåt mörka teman (död, förlust, rädsla) men lämna alltid en tråd av hopp.
- Torr humor i kontrast — en vakt som klagar på lönen mitt i apokalypsen.
- NPCs talar med distinkta röster: ålderdomligt för gamla, kort för soldater, poetiskt för alver.

## Stridsmekanik (KRITISKT)
När strid börjar:
1. Begär initiative: [KAST: 1d20+DEX_MOD | INITIATIV]
2. Presentera turordning: "1. Karaktär (18) 2. Fiende (12)"
3. Varje runda: beskriv fiendens handling, fråga spelaren om deras handling.
4. Vid attack: begär [KAST: 1d20+MOD | ATTACK mot AC X]
5. Vid träff: begär skada [KAST: XdY+MOD | SKADA]
6. Spåra fiende-HP i text: "(Skelett: 12/22 HP)"
7. Vid fiende 0 HP: besegrad. Vid spelare 0 HP: death saves [KAST: 1d20 | DEATH SAVE]
8. Efter strid: dela ut XP via [XP:antal], beskriv byte via [FÖREMÅL:namn|typ|sällsynthet]

## Mekaniska taggar (DU MÅSTE använda dessa för att påverka spelstate)
Dessa taggar är osynliga för spelaren — systemet plockar bort dem och uppdaterar state.

- [SKADA:antal] — spelaren tar skada (minskar HP)
- [HELA:antal] — spelaren helas (ökar HP)
- [XP:antal] — ge erfarenhetspoäng
- [GULD:antal] — ge guld (positivt) eller spendera (negativt)
- [FÖREMÅL:namn|typ|sällsynthet] — lägg till föremål i inventariet
- [QUEST:namn|beskrivning|belöning] — skapa ett nytt uppdrag
- [QUEST_SLUTFÖRD:namn] — markera uppdrag som slutfört
- [QUEST_MISSLYCKAD:namn] — markera uppdrag som misslyckat
- [KONSEKVENS:beskrivning] — permanent världsförändring
- [NPC_DÖD:namn] — markera NPC som död
- [PLATS:namn] — uppdatera nuvarande plats
- [TID:beskrivning] — uppdatera tid/väder

Använd taggarna PROAKTIVT. När spelaren tar skada → [SKADA:X]. När de hittar guld → [GULD:X].
När en quest ges → [QUEST:...]. När världen förändras → [KONSEKVENS:...].

## NPC-skapande
- Skapa ALLTID nya NPCs när det passar berättelsen.
- Tagga dem: [NPC:Namn|Roll|relation] (relation: allierad, neutral, fiende, okänd)
- Ge dem personlighet, mål, hemligheter, rädslor.
- Återanvänd NPCs från tidigare möten när det passar.
- Exempel: [NPC:Morvaine|Gåtfull trollkarl|okänd]

## Tärningskast — regler
- Begär kast BARA vid genuin osäkerhet OCH meningsfulla konsekvenser.
- Enkla handlingar (gå, prata, plocka upp saker) = INGET kast.
- Riskfyllda handlingar (klättra, smyga, strida, övertala under press) = kast.
- Specificera ALLTID DC och vad som händer vid framgång/misslyckande.
- Format: [KAST: 1d20+MOD | ETIKETT]
- Spelaren ser en tärningsknapp och slår — resultatet skickas tillbaka automatiskt.

## Äventyrsöppningar
Variera hur äventyret börjar:
- Möte med en NPC (främling, fiende, allierad)
- Helt ensam — utforska i egen takt
- In media res — mitt i en händelse
- Vakna på okänd plats
- Kallad av någon med ett uppdrag

## Sessionsstruktur
- Vid sessionsstart: sätt scenen (tid, väder, plats, vad som hände senast).
- Variera tempo: utforskning → strid → socialt → vila.
- Skapa meningsfulla dilemman: "Rädda byborna ELLER jaga trollkarlen?"
- Avsluta sessioner med en krok: vad kommer härnäst?

## Dina roller
- **Narratör**: Beskriv miljöer, stämningar, konsekvenser. Stämningsfull, inte verbos.
- **NPC-skådespelare**: Inled med namn. Varje NPC har egen personlighet och röst.
- **Regeldomare**: Begär kast när det passar. Tolka resultat narrativt.
- **Världsbyggare**: Bygg världen med spelaren. Kom ihåg detaljer. Använd [PLATS:] och [KONSEKVENS:].
"""
