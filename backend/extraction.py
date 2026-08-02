"""
The Lore Weaver's Cauldron — Faktextrahering & Faktaregister
=================================================
Extraherar strukturerade fakta ur DM-svar med en billig/snabb LLM
och lagrar dem i ett per-användare JSON-register.

Flöde:
  1. DM genererar ett svar + spelaren gör en handling.
  2. extract_facts() skickar båda till en snabb modell med en
     extraheringsprompt → får tillbaka en JSON-lista av fakta.
  3. FactRegister.add_facts() deduplicerar, versionerar och sparar.
  4. Inför nästa DM-svar anropas get_relevant_facts() + format_facts_block()
     för att injicera auktoritativ kontext i systemprompten.

Faktakategorier:
  npc          – ny information om en NPC
  location     – platser som nämns eller beskrivs
  item         – föremål som hittas, tappas eller förstörs
  event        – betydelsefulla händelser
  promise      – löften/åtaganden (NPC eller spelare)
  world        – världstillståndsändringar (väder, tid, politik …)
  relationship – relationsändringar mellan NPC:er eller NPC↔spelare

Användning:
    from extraction import FactRegister, extract_facts, format_facts_block

    reg = FactRegister("rostad")
    facts = await extract_facts(dm_reply, player_input, turn=5,
                                model_call_fn=call_cheap_llm)
    reg.add_facts(facts)
    relevant = reg.get_relevant_facts("borgmästare Hilda")
    block = format_facts_block(relevant)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Coroutine, Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("morkrets.extraction")

# ═══════════════════════════════════════
# SÖKVÄGAR
# ═══════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CAMPAIGNS_DIR = _DATA_DIR / "campaigns"

# ═══════════════════════════════════════
# 1. FAKTAMODELL (Pydantic)
# ═══════════════════════════════════════

FactCategory = Literal[
    "npc", "location", "item", "event", "promise", "world", "relationship"
]

# Category labels for prompt formatting (SV default + EN)
CATEGORY_LABELS: dict[str, str] = {
    "npc": "NPC",
    "location": "PLATS",
    "item": "FÖREMÅL",
    "event": "HÄNDELSE",
    "promise": "LÖFTE",
    "world": "VÄRLD",
    "relationship": "RELATION",
}

CATEGORY_LABELS_EN: dict[str, str] = {
    "npc": "NPC",
    "location": "LOCATION",
    "item": "ITEM",
    "event": "EVENT",
    "promise": "PROMISE",
    "world": "WORLD",
    "relationship": "RELATIONSHIP",
}


class Fact(BaseModel):
    """Ett enskilt faktum extraherat ur ett DM-svar."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: FactCategory
    text: str = Field(..., min_length=1, description="Beskrivning på svenska")
    source_turn: int = Field(..., ge=0, description="Vilken tur faktat kommer från")
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Konfidens 0–1"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    superseded_by: Optional[str] = Field(
        default=None, description="ID på det faktum som ersätter detta"
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, v: str) -> str:
        """Tillåt svenska kategorinamn från LLM-svar."""
        v = v.strip().lower()
        mapping = {
            "npc": "npc",
            "plats": "location",
            "location": "location",
            "föremål": "item",
            "foremal": "item",
            "item": "item",
            "händelse": "event",
            "handelse": "event",
            "event": "event",
            "löfte": "promise",
            "lofte": "promise",
            "promise": "promise",
            "värld": "world",
            "varld": "world",
            "world": "world",
            "relation": "relationship",
            "relationship": "relationship",
        }
        return mapping.get(v, v)


# ═══════════════════════════════════════
# 2. EXTRACTION PROMPTS (SV + EN)
# ═══════════════════════════════════════

EXTRACTION_SYSTEM_PROMPT = """\
Du är en faktextraherare för ett D&D 5e-rollspel.
Din uppgift: läs DM-svaret och spelarens handling, och extrahera ALLA \
nya, beständiga fakta som påverkar spelvärlden.

## Kategorier
- npc: Ny information om en NPC (namn, roll, personlighet, mål, död …)
- location: Platser som nämns, beskrivs eller blir tillgängliga
- item: Föremål som hittas, tappas, förstörs eller ges
- event: Betydelsefulla händelser (strider, möten, upptäckter …)
- promise: Löften eller åtaganden som görs av NPC:er eller spelaren
- world: Världstillståndsändringar (väder, tid, politiska skeenden …)
- relationship: Relationsändringar (NPC↔spelare eller NPC↔NPC)

## Regler
1. Skriv varje faktum på SAMMA SPRÅK som indatatexten (svenska eller engelska), kort och konkret (max ~120 tecken).
2. Ta bara med NY information — upprepa inte saker som redan är kända.
3. Inkludera inte mekaniska taggar ([SKADA:n], [XP:n] osv.) i texten.
4. Sätt confidence 0.9–1.0 för explicita fakta, 0.6–0.8 för underförstådda.
5. Returnera ENDAST ett JSON-objekt. Ingen markdown, ingen förklaring.

## Inventory-ändringar
Utöver fakta ska du identifiera om spelaren FÅR eller FÖRLORAR föremål.
- "add": Spelaren tar emot, hittar, köper, stjäl eller får ett föremål.
- "remove": Spelaren tappar, ger bort, säljer, förbrukar eller förlorar ett föremål.
- Ta ENDAST med föremål som faktiskt byter ägare — inte saker som bara nämns.
- "Du siktar mot flaskan" → NEJ. "Du tar flaskan" → JA.
- Skippa föremål som redan finns i "Nuvarande inventory" (nedan) om de inte \
faktiskt ges/tas igen.
- Ange type (Vapen, Rustning, Dryck, Magisk, Verktyg, Annat) och qty (default 1).

## Format
{
  "facts": [
    {"category": "npc", "text": "...", "confidence": 0.9}
  ],
  "inventory_changes": [
    {"action": "add", "name": "Rostigt svärd", "type": "Vapen", "qty": 1},
    {"action": "remove", "name": "Torkat kött", "qty": 1}
  ]
}

## Exempel

DM-svar: "Borgmästare Hilda stirrar på dig. 'Jag litar inte på äventyrare', \
fräser hon. Bakom henne skymtar du en karta över Gråvakts grottor. \
[NPC:Borgmästare Hilda|Borgmästare|fiende] [PLATS:Gråvakts grottor]"
Spelare: "Jag försöker övertala henne att ge oss uppdraget."

→ {
  "facts": [
    {"category": "npc", "text": "Borgmästare Hilda är fientligt inställd till spelaren och litar inte på äventyrare", "confidence": 0.95},
    {"category": "location", "text": "Gråvakts grottor finns på en karta i borgmästarens rum", "confidence": 0.8},
    {"category": "relationship", "text": "Borgmästare Hilda är fiende till spelaren", "confidence": 0.95}
  ],
  "inventory_changes": []
}

DM-svar: "Du öppnar kistan och finner ett rostigt svärd och 15 guldmyn. \
[FÖREMÅL:Rostigt svärd|Vapen|vanlig] [GULD:15]"
Spelare: "Jag tar svärdet och guldet."

→ {
  "facts": [
    {"category": "item", "text": "Spelaren hittade ett rostigt svärd (vanligt vapen) i en kista", "confidence": 0.95},
    {"category": "item", "text": "Spelaren plockade upp 15 guldmyn", "confidence": 0.9}
  ],
  "inventory_changes": [
    {"action": "add", "name": "Rostigt svärd", "type": "Vapen", "qty": 1}
  ]
}

DM-svar: "Vakten nickar långsamt. 'Jag ska visa dig vägen imorgon bitti, \
men var här före gryningen.' [NPC_RELATION:Vakten|allierad]"
Spelare: "Bra, jag vilar här inatt."

→ {
  "facts": [
    {"category": "promise", "text": "Vakten lovade att visa spelaren vägen imorgon före gryningen", "confidence": 0.95},
    {"category": "relationship", "text": "Vakten är nu allierad med spelaren", "confidence": 0.9}
  ],
  "inventory_changes": []
}

Om inga nya fakta eller inventory-ändringar finns:
{"facts": [], "inventory_changes": []}
"""

# English extraction prompt
EXTRACTION_SYSTEM_PROMPT_EN = """\
You are a fact extractor for a D&D 5e RPG.
Your task: read the DM reply and the player's action, and extract ALL \
new, persistent facts that affect the game world.

## Categories
- npc: New information about an NPC (name, role, personality, goals, death …)
- location: Places mentioned, described, or made available
- item: Items found, dropped, destroyed, or given
- event: Significant events (battles, encounters, discoveries …)
- promise: Promises or commitments made by NPCs or the player
- world: World state changes (weather, time, political events …)
- relationship: Relationship changes (NPC↔player or NPC↔NPC)

## Rules
1. Write each fact in English, short and concrete (max ~120 characters).
2. Only include NEW information — do not repeat things already known.
3. Do not include mechanical tags ([SKADA:n], [XP:n] etc.) in the text.
4. Set confidence 0.9–1.0 for explicit facts, 0.6–0.8 for implied ones.
5. Return ONLY a JSON object. No markdown, no explanation.

## Inventory changes
In addition to facts, identify if the player GAINS or LOSES items.
- "add": Player receives, finds, buys, steals, or gains an item.
- "remove": Player drops, gives away, sells, consumes, or loses an item.
- ONLY include items that actually change hands — not things merely mentioned.
- "You aim at the bottle" → NO. "You take the bottle" → YES.
- Skip items already in "Current inventory" (below) unless given/taken again.
- Specify type (Weapon, Armor, Potion, Magic, Tool, Other) and qty (default 1).

## Format
{
  "facts": [
    {"category": "npc", "text": "...", "confidence": 0.9}
  ],
  "inventory_changes": [
    {"action": "add", "name": "Rusty sword", "type": "Weapon", "qty": 1},
    {"action": "remove", "name": "Dried meat", "qty": 1}
  ]
}

## Examples

DM reply: "Mayor Hilda stares at you. 'I don't trust adventurers,' \
she hisses. Behind her you glimpse a map of Greywatch Caverns. \
[NPC:Mayor Hilda|Mayor|enemy] [LOCATION:Greywatch Caverns]"
Player: "I try to persuade her to give us the quest."

→ {
  "facts": [
    {"category": "npc", "text": "Mayor Hilda is hostile toward the player and distrusts adventurers", "confidence": 0.95},
    {"category": "location", "text": "Greywatch Caverns appears on a map in the mayor's room", "confidence": 0.8},
    {"category": "relationship", "text": "Mayor Hilda is an enemy of the player", "confidence": 0.95}
  ],
  "inventory_changes": []
}

DM reply: "You open the chest and find a rusty sword and 15 gold coins. \
[ITEM:Rusty sword|Weapon|common] [GOLD:15]"
Player: "I take the sword and the gold."

→ {
  "facts": [
    {"category": "item", "text": "Player found a rusty sword (common weapon) in a chest", "confidence": 0.95},
    {"category": "item", "text": "Player picked up 15 gold coins", "confidence": 0.9}
  ],
  "inventory_changes": [
    {"action": "add", "name": "Rusty sword", "type": "Weapon", "qty": 1}
  ]
}

If no new facts or inventory changes exist:
{"facts": [], "inventory_changes": []}
"""

# User prompt templates — filled per call (SV + EN)
_EXTRACTION_USER_TEMPLATE = """\
## DM-svar (tur {turn})
{dm_reply}

## Spelarens handling
{player_input}

## Nuvarande inventory
{inventory_list}

Extrahera fakta och inventory-ändringar som JSON-objekt:"""

_EXTRACTION_USER_TEMPLATE_EN = """\
## DM reply (turn {turn})
{dm_reply}

## Player's action
{player_input}

## Current inventory
{inventory_list}

Extract facts and inventory changes as a JSON object:"""


# ═══════════════════════════════════════
# 3. EXTRHERINGSFUNKTION
# ═══════════════════════════════════════

# Typalias för den LLM-callable som anroparen tillhandahåller
ModelCallFn = Callable[[list[dict]], Coroutine[None, None, str]]


def _strip_markdown_json(raw: str) -> str:
    """Ta bort markdown-kodblock runt JSON (```json ... ```)."""
    raw = raw.strip()
    # Ta bort ```json ... ``` eller ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw


def _extract_json_array(raw: str) -> list[dict] | None:
    """
    Försök parsa en JSON-array ur LLM-svaret.
    Hanterar markdown-inpackning och text runt JSON.
    Returnerar None om parsing misslyckas.
    """
    cleaned = _strip_markdown_json(raw)

    # Direkt försök
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Försök hitta första [ ... ] i texten
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _extract_json_object(raw: str) -> dict | None:
    """
    Försök parsa ett JSON-objekt ur LLM-svaret.
    Hanterar markdown-inpackning, text runt JSON, och bakåtkompatibilitet
    (ren array → {"facts": [...], "inventory_changes": []}).
    """
    cleaned = _strip_markdown_json(raw)

    # Direkt försök
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
        # Bakåtkompat: ren array → wrappa
        if isinstance(data, list):
            return {"facts": data, "inventory_changes": []}
    except json.JSONDecodeError:
        pass

    # Försök hitta första { ... } i texten
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: ren array i texten
    arr = _extract_json_array(raw)
    if arr is not None:
        return {"facts": arr, "inventory_changes": []}

    return None


async def extract_facts(
    dm_reply: str,
    player_input: str,
    turn: int,
    model_call_fn: ModelCallFn,
    inventory_list: str = "(tomt)",
    language: str = "sv",
) -> tuple[list[Fact], list[dict]]:
    """
    Extrahera strukturerade fakta + inventory-ändringar ur ett DM-svar.

    Anropar model_call_fn (en async callable som tar messages-lista och
    returnerar str) med extraheringsprompten. Parsar JSON, validerar
    med Pydantic. Vid felaktig JSON: försök en gång till, annars tom lista.

    Args:
        dm_reply: DM:ns svarstext (ren, utan mekaniska taggar).
        player_input: Spelarens handling.
        turn: Aktuellt turnummer.
        model_call_fn: Async funktion (messages) -> str, tillhandahålls
                       av anroparen (t.ex. en wrapper kring httpx + billig modell).
        inventory_list: Formaterad lista av nuvarande inventory (för dedup-kontext).
        language: Campaign language ('sv' or 'en') — selects prompt language.

    Returns:
        Tuple: (lista av validerade Fact-objekt, lista av inventory-change dicts).
    """
    # Select prompt language
    if language == "en":
        system_prompt = EXTRACTION_SYSTEM_PROMPT_EN
        user_template = _EXTRACTION_USER_TEMPLATE_EN
    else:
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        user_template = _EXTRACTION_USER_TEMPLATE

    user_msg = user_template.format(
        turn=turn, dm_reply=dm_reply, player_input=player_input,
        inventory_list=inventory_list,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    # Två försök: ordinarie + retry vid felaktig JSON
    for attempt in range(2):
        try:
            raw_response = await model_call_fn(messages)
        except Exception:
            logger.exception("LLM-anrop misslyckades (försök %d)", attempt + 1)
            if attempt == 0:
                continue
            return [], []

        parsed = _extract_json_object(raw_response)
        if parsed is None:
            logger.warning(
                "Kunde inte parsa JSON från extrahering (försök %d). "
                "Rådata: %.200s",
                attempt + 1,
                raw_response,
            )
            if attempt == 0:
                # Lägg till en rättledande hint och försök igen
                messages.append({"role": "assistant", "content": raw_response})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Svaret var inte giltig JSON. "
                            'Returnera ENDAST ett JSON-objekt med "facts" och '
                            '"inventory_changes", inget annat.'
                        ),
                    }
                )
                continue
            return [], []

        # Validera varje faktum med Pydantic
        facts: list[Fact] = []
        for item in parsed.get("facts", []):
            try:
                fact = Fact(
                    category=item.get("category", "event"),
                    text=item.get("text", ""),
                    source_turn=turn,
                    confidence=float(item.get("confidence", 0.8)),
                )
                facts.append(fact)
            except Exception:
                logger.debug("Skipped invalid fact: %s", item)
                continue

        # Validera inventory-ändringar
        inv_changes: list[dict] = []
        for ch in parsed.get("inventory_changes", []):
            action = ch.get("action", "").lower()
            name = ch.get("name", "").strip()
            if action not in ("add", "remove") or not name:
                continue
            inv_changes.append({
                "action": action,
                "name": name,
                "type": ch.get("type", "Annat"),
                "qty": max(1, int(ch.get("qty", 1))),
            })

        logger.info(
            "Extraherade %d fakta + %d inventory-ändringar från tur %d (försök %d)",
            len(facts), len(inv_changes), turn, attempt + 1,
        )
        return facts, inv_changes

    return [], []  # Nåbar bara om båda försöken misslyckas


# ═══════════════════════════════════════
# 4. FAKTAREGISTER
# ═══════════════════════════════════════

# Stopwords for relevance scoring (SV + EN)
_STOPWORDS = frozenset(
    "och att den det en ett i på för med som av till är var ha de "
    "jag mig min dig din han hon vi ni oss er dem deras dess detta "
    "dessa från vid om men eller inte kan ska kommer blev blir vara "
    "har hade också mycket väldigt bara".split()
)

_STOPWORDS_EN = frozenset(
    "the a an and or but in on at to for of with by from as is was "
    "were be been being have has had do does did will would shall "
    "should may might can could this that these those it its he she "
    "they we you i me my his her their our your not no nor so if "
    "then than too very just about also".split()
)

_ALL_STOPWORDS = _STOPWORDS | _STOPWORDS_EN


def _tokenize(text: str) -> set[str]:
    """Split text into meaningful words (lowercase, without stopwords)."""
    words = re.findall(r"[a-zåäö0-9]+", text.lower())
    return {w for w in words if w not in _ALL_STOPWORDS and len(w) > 1}


def _token_overlap_ratio(a: str, b: str) -> float:
    """
    Beräkna överlappningsgrad mellan två texter.
    Returnerar andelen delade tokens relativt den minsta mängden.
    """
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = tokens_a & tokens_b
    return len(overlap) / min(len(tokens_a), len(tokens_b))


class FactRegister:
    """
    Per-kampanj faktaregister med JSON-lagring.

    Fil: backend/data/campaigns/<username>/<campaign_id>/facts.json
    """

    def __init__(self, username: str, campaign_id: str = "", data_dir: Path | None = None):
        self._username = username
        base = data_dir or _CAMPAIGNS_DIR
        if campaign_id:
            self._path = base / username / campaign_id / "facts.json"
        else:
            # Fallback: per-användare (bakåtkompatibilitet)
            self._path = base / username / "facts.json"
        self._facts: list[Fact] = []
        self._load()

    # ── Persistens ──────────────────────

    def _load(self) -> None:
        """Ladda fakta från disk (tom lista om filen saknas)."""
        if not self._path.exists():
            self._facts = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._facts = [Fact.model_validate(item) for item in raw]
            logger.info(
                "Laddade %d fakta för %s", len(self._facts), self._username
            )
        except Exception:
            logger.exception(
                "Kunde inte ladda facts.json för %s — börjar tomt",
                self._username,
            )
            self._facts = []

    def save(self) -> None:
        """Spara alla fakta till disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [f.model_dump() for f in self._facts]
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug("Sparade %d fakta till %s", len(data), self._path)

    # ── Lägg till / deduplicera ────────

    def add_facts(self, facts: list[Fact]) -> int:
        """
        Lägg till nya fakta med deduplicering och superseding.

        Deduplicering: exakt matchning eller >90 % tokenöverlapp → hoppa över.
        Superseding: om ett befintligt faktum i samma kategori har >60 %
        överlapp (samma entitet, uppdaterad info), markeras det gamla som
        ersatt (superseded_by = nytt ID) och det nya läggs till.

        Returns:
            Antal nya fakta som lades till.
        """
        added = 0
        for new_fact in facts:
            # Kontrollera mot alla aktiva (inte ersatta) fakta
            is_duplicate = False
            for existing in self._facts:
                if existing.superseded_by is not None:
                    continue  # Ersatta fakta jämförs inte

                ratio = _token_overlap_ratio(new_fact.text, existing.text)

                # Exakt eller nästan exakt matchning → hoppa över
                if new_fact.text.strip() == existing.text.strip() or ratio > 0.90:
                    is_duplicate = True
                    break

                # Samma kategori + tydlig överlapp → ersätt det gamla
                if new_fact.category == existing.category and ratio > 0.60:
                    existing.superseded_by = new_fact.id
                    logger.debug(
                        "Ersatte faktum '%s' → '%s'",
                        existing.text[:60],
                        new_fact.text[:60],
                    )

            if not is_duplicate:
                self._facts.append(new_fact)
                added += 1

        if added:
            self.save()
            logger.info(
                "Lade till %d nya fakta (%d duplicerade hoppade över)",
                added,
                len(facts) - added,
            )
        return added

    # ── Frågor ──────────────────────────

    def _active_facts(self) -> list[Fact]:
        """Alla fakta som inte är ersatta."""
        return [f for f in self._facts if f.superseded_by is None]

    def get_relevant_facts(self, query: str, limit: int = 10) -> list[Fact]:
        """
        Hitta relevanta fakta med nyckelordsbaserad scoring.

        Scoring: ordöverlapp mellan fråga och faktatext,
        med bonus för nyare fakta (högre turn = högre score).
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        active = self._active_facts()
        if not active:
            return []

        # Högsta turn för recentsboost
        max_turn = max((f.source_turn for f in active), default=1) or 1

        scored: list[tuple[float, Fact]] = []
        for fact in active:
            fact_tokens = _tokenize(fact.text)
            overlap = query_tokens & fact_tokens
            if not overlap:
                continue
            # Bas: andel överlappande ord
            base_score = len(overlap) / len(query_tokens)
            # Recentsboost: nyare fakta får upp till +30 %
            recency = 0.3 * (fact.source_turn / max_turn)
            # Konfidensvikt
            score = (base_score + recency) * (0.5 + 0.5 * fact.confidence)
            scored.append((score, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [fact for _, fact in scored[:limit]]

    def get_facts_by_category(self, category: str) -> list[Fact]:
        """Hämta alla aktiva fakta i en given kategori."""
        return [
            f
            for f in self._active_facts()
            if f.category == category
        ]

    def format_for_prompt(self, facts: list[Fact]) -> str:
        """
        Formatera en lista fakta som kompakt text för DM-systemprompten.
        Använder format_facts_block() under huven.
        """
        return format_facts_block(facts)

    def stats(self) -> dict:
        """Antal fakta per kategori (aktiva + totalt)."""
        active = self._active_facts()
        active_counts: Counter[str] = Counter(f.category for f in active)
        total_counts: Counter[str] = Counter(f.category for f in self._facts)
        return {
            "total": len(self._facts),
            "active": len(active),
            "superseded": len(self._facts) - len(active),
            "by_category_active": dict(active_counts),
            "by_category_total": dict(total_counts),
        }


# ═══════════════════════════════════════
# 5. INTEGRATIONSHELPERS
# ═══════════════════════════════════════


def format_facts_block(facts: list[Fact], language: str = "sv") -> str:
    """
    Format facts as an authoritative block for the DM system prompt.

    Example:
        ## FAKTAREGISTER (auktoritativt — motsäg aldrig)
        - [NPC] Borgmästare Hilda är fientligt inställd till spelaren (tur 12)
        - [PLATS] Grottan vid Gråvakt har en hemlig ingång (tur 8)
    """
    if not facts:
        return ""

    labels = CATEGORY_LABELS_EN if language == "en" else CATEGORY_LABELS
    header = "## FACT REGISTER (authoritative — never contradict)" if language == "en" \
        else "## FAKTAREGISTER (auktoritativt — motsäg aldrig)"
    turn_word = "turn" if language == "en" else "tur"

    lines = [header]
    for fact in facts:
        label = labels.get(fact.category, fact.category.upper())
        lines.append(f"- [{label}] {fact.text} ({turn_word} {fact.source_turn})")
    return "\n".join(lines)
