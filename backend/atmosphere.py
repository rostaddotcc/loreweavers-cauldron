"""
Mörkrets Rike — Atmosfär-subagent
===================================
Analyserar DM-svar och genererar ASCII/CLI-art inline.
Kör på en snabb modell (qwen3.6-flash / deepseek-v4-flash).
"""

import re

# ── Cooldown: max 1 art per ART_COOLDOWN meddelanden ──
ART_COOLDOWN = 3

# ── Miljöer som triggar ambient ASCII-art ──
# Situationella miljöer först (högre prioritet)
ENVIRONMENTS = {
    'strid': ['strid', 'combat', 'attack', 'blod', 'blood', 'vapen', 'weapon',
              'fight', 'slåss', 'svärd', 'sword', 'strids', 'anfall', 'försvar',
              'pil', 'arrow', 'sköld', 'shield', 'hugg', 'slag'],
    'död': ['död', 'death', 'die', 'corpse', 'lik', 'grave', 'skull',
            'dödskalle', 'gravsten', 'kista', 'avliden', 'stupad', 'livlös'],
    'vila': ['vila', 'rest', 'camp', 'läger', 'sleep', 'sömn', 'sova',
             'rast', 'tält', 'bras', 'eldst', 'nattläger'],
    'upptäckt': ['upptäckt', 'discovery', 'find', 'hitta', 'treasure', 'skatt',
                 'secret', 'hemlig', 'door', 'dörr', 'port', 'gömd', 'funnen',
                 'kammare', 'valv'],
    'skog': ['skog', 'träd', 'gran', 'björk', 'lövv', 'snår', 'glänta', 'rot',
             'mossa', 'svamp'],
    'is': ['is', 'snö', 'frost', 'glaciär', 'kyla', 'vinter', 'tjäle', 'istapp'],
    'lava': ['lava', 'magma', 'vulkan', 'glöd', 'hetta', 'aska', 'brinnande'],
    'grotta': ['grotta', 'tunnel', 'håla', 'underjord', 'sten', 'klippa',
               'gruva', 'kaverna'],
    'vatten': ['vatten', 'river', 'sea', 'lake', 'rain', 'regn', 'bäck', 'fors',
               'vattenfall', 'ström'],
    'hav': ['hav', 'sjö', 'våg', 'strand', 'kust', 'djup'],
    'slott': ['slott', 'borg', 'torn', 'mur', 'fästning', 'ruin', 'tron'],
    'grav': ['grav', 'kyrkogård', 'krypta', 'gravkammare', 'ben', 'skelett'],
    'stad': ['stad', 'by', 'torg', 'gata', 'hus', 'värdshus', 'marknad', 'gränd'],
    'berg': ['berg', 'topp', 'klättra', 'dal', 'pass', 'höjd', 'utsikt', 'stup',
             'mountain', 'cliff', 'peak', 'cave'],
    'träsk': ['träsk', 'mosse', 'sump', 'gyttja', 'dimma', 'kärr', 'vass'],
}

MAX_ART_PER_REPLY = 1

# ── Atmosfäriska prompter per miljö ──
ENV_PROMPTS = {
    'skog': (
        'draw a dark, oppressive forest with twisted trees, fog between the trunks, '
        'and a faint green glow from something hidden. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'is': (
        'draw a frozen wasteland with jagged ice formations, blowing snow, '
        'and a pale cold moon hanging low. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'lava': (
        'draw a volcanic hellscape with rivers of lava, erupting sparks, '
        'and black rock silhouettes against an orange glow. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'grotta': (
        'draw a deep cave with stalactites dripping, narrow passages, '
        'and something glowing faintly in the darkness ahead. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'vatten': (
        'draw a misty river winding through dark rocks, rain falling, '
        'with a faint reflection shimmering on the water surface. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'hav': (
        'draw a dark ocean with crashing waves, a lonely shore, '
        'and storm clouds gathering on the horizon. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'slott': (
        'draw a crumbling castle with broken towers, ivy on the walls, '
        'and a single lit window high up in the dark. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'grav': (
        'draw a haunted graveyard with crooked gravestones, dead trees, '
        'and mist rising from the cold ground. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'stad': (
        'draw a medieval city street at dusk with crooked houses, '
        'a hanging sign, and wet cobblestones reflecting torchlight. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'berg': (
        'draw a mountain peak above the clouds with a narrow cliff path, '
        'wind-swept and vertiginous, a hawk circling. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'träsk': (
        'draw a foggy swamp with reeds, murky water, will-o-wisps, '
        'and gnarled dead trees reaching upward. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'strid': (
        'draw a chaotic battle scene with crossed swords, flying arrows, '
        'splashing blood, and a fallen shield on the ground. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'död': (
        'draw a scene of death: a skull, scattered bones, a snuffed candle, '
        'and darkness closing in from all sides. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'vila': (
        'draw a campfire at night with sparks rising into the dark, '
        'a tent silhouette, and stars above. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
    'upptäckt': (
        'draw a hidden treasure: an open chest glowing, scattered coins, '
        'a secret door ajar with golden light spilling out. Max 12 lines, 50 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'Make it feel like a DOS game from 1993. No text labels.'
    ),
}

# ── Event-triggered art (från mekaniska effekter) ──
EVENT_ART = {
    'level_up': (
        'draw a triumphant pillar of light breaking through darkness, '
        'rays spreading upward, sparks and energy radiating. Max 8 lines, 40 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'DOS game style, 1993. No text labels.'
    ),
    'npc_död': (
        'draw a lonely gravestone with a cross, dead grass around it, '
        'and a crow perched on top. Max 8 lines, 40 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'DOS game style, 1993. No text labels.'
    ),
    'ny_dag': (
        'draw a sunrise over dark hills, rays breaking the horizon, '
        'birds silhouetted in the sky. Max 8 lines, 40 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'DOS game style, 1993. No text labels.'
    ),
    'quest': (
        'draw an unrolled scroll with a wax seal, banner ribbons, '
        'and a quill resting beside it. Max 8 lines, 40 chars wide. '
        'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
        'DOS game style, 1993. No text labels.'
    ),
}

# Event-typ → CSS-klassnamn för frontend (undvik icke-ASCII i klassnamn)
EVENT_CSS_CLASS = {
    'level_up': 'art-level-up',
    'npc_död': 'art-death',
    'ny_dag': 'art-new-day',
    'quest': 'art-quest',
}

# Event-typ → frontend-etikett
EVENT_LABEL = {
    'level_up': '✦ nivå upp ✦',
    'npc_död': '✦ vila i frid ✦',
    'ny_dag': '✦ ny dag ✦',
    'quest': '✦ uppdrag ✦',
}


def detect_environments(text: str) -> list[str]:
    """Hitta vilka miljöer som nämns i texten."""
    text_lower = text.lower()
    found = []
    for env, keywords in ENVIRONMENTS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(env)
                break
    return found[:MAX_ART_PER_REPLY]


def build_art_prompt(environment: str) -> str:
    """Bygg prompt för ambient ASCII-art generering."""
    desc = ENV_PROMPTS.get(environment)
    if not desc:
        desc = (
            f'draw an atmospheric scene of: {environment}. '
            'Max 12 lines, 50 chars wide. '
            'Use only these characters: / \\ | - _ . : ; # @ * ^ ~ + =. '
            'DOS game style, 1993. No text labels.'
        )
    return (
        "You are an ASCII artist for a dark fantasy RPG. "
        "Create a compact, moody ASCII art scene.\n\n"
        f"{desc}\n\n"
        "CRITICAL RULES:\n"
        "- ONLY use these characters: / \\ | - _ . : ; # @ * ^ ~ + =\n"
        "- NO letters, NO words, NO text labels anywhere in the art\n"
        "- NO markdown, NO code fences, NO explanations\n"
        "- Respond with ONLY the ASCII art, nothing else\n"
        "- Make it feel hand-crafted, atmospheric, like a lost DOS game artifact"
    )


def build_event_art_prompt(event_type: str) -> str | None:
    """Bygg prompt för event-triggered ASCII-art (level_up, npc_död, etc.)."""
    desc = EVENT_ART.get(event_type)
    if not desc:
        return None
    return (
        "You are an ASCII artist for a dark fantasy RPG. "
        "Create a small, impactful ASCII art moment.\n\n"
        f"{desc}\n\n"
        "CRITICAL RULES:\n"
        "- ONLY use these characters: / \\ | - _ . : ; # @ * ^ ~ + =\n"
        "- NO letters, NO words, NO text labels anywhere in the art\n"
        "- NO markdown, NO code fences, NO explanations\n"
        "- Respond with ONLY the ASCII art, nothing else\n"
        "- Keep it small and iconic — a single powerful image"
    )


def should_generate_art(meta: dict, turn_count: int) -> bool:
    """Cooldown: max 1 art per ART_COOLDOWN meddelanden."""
    last = meta.get('last_art_turn', -ART_COOLDOWN)
    return (turn_count - last) >= ART_COOLDOWN


def postprocess_art(raw: str) -> str | None:
    """
    Kvalitetskontroll av LLM-genererad ASCII-art.
    - Ta bort rader längre än 55 tecken
    - Ta bort rader som innehåller bokstäver (ska vara rena symboler)
    - Max 14 rader
    - Släng om < 3 rader kvar (visa inte skräp)
    """
    if not raw:
        return None

    # Ta bort markdown code fences
    art = raw.strip()
    if art.startswith("```"):
        art = re.sub(r"^```[a-z]*\n?", "", art)
        art = re.sub(r"\n?```$", "", art)
        art = art.strip()

    lines = art.split('\n')
    cleaned = []
    for line in lines:
        # Strip rader längre än 55 tecken
        if len(line) > 55:
            continue
        # Ta bort rader med bokstäver (konsten ska vara rena symboler)
        if re.search(r'[a-zA-ZåäöÅÄÖ]', line):
            continue
        cleaned.append(line.rstrip())

    # Ta bort tomma rader i början/slutet
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    # Max 14 rader
    cleaned = cleaned[:14]

    # Släng om mindre än 3 rader
    if len(cleaned) < 3:
        return None

    return '\n'.join(cleaned)
