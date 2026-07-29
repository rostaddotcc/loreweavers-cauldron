"""
Mörkrets Rike — Atmosfär-subagent
===================================
Analyserar DM-svar och genererar ASCII/CLI-art inline.
Primär: LLM-generering via MiMo 2.5. Fallback: förgenererad art-bank.
"""

import re
import random

# ── Cooldown: max 1 art per ART_COOLDOWN meddelanden ──
ART_COOLDOWN = 2

# ── Miljöer som triggar ambient ASCII-art ──
ENVIRONMENTS = {
    'strid': ['strid', 'combat', 'attack', 'blod', 'blood', 'vapen', 'weapon',
              'fight', 'slåss', 'svärd', 'sword', 'strids', 'anfall', 'försvar',
              'pil', 'arrow', 'sköld', 'shield', 'hugg', 'slag', 'fiende',
              'monster', 'varelse', 'best', 'krig', 'battle'],
    'död': ['död', 'death', 'die', 'corpse', 'lik', 'grave', 'skull',
            'dödskalle', 'gravsten', 'kista', 'avliden', 'stupad', 'livlös',
            'skelett', 'ben', 'rutten'],
    'vila': ['vila', 'rest', 'camp', 'läger', 'sleep', 'sömn', 'sova',
             'rast', 'tält', 'bras', 'eldst', 'nattläger', 'eld', 'flamma',
             'gnista', 'värme'],
    'upptäckt': ['upptäckt', 'discovery', 'find', 'hitta', 'treasure', 'skatt',
                 'secret', 'hemlig', 'door', 'dörr', 'port', 'gömd', 'funnen',
                 'kammare', 'valv', 'kista', 'guld', 'juvel'],
    'skog': ['skog', 'träd', 'gran', 'björk', 'lövv', 'snår', 'glänta', 'rot',
             'mossa', 'svamp', 'gren', 'stam', 'lövsal', 'dungel'],
    'is': ['is', 'snö', 'frost', 'glaciär', 'kyla', 'vinter', 'tjäle', 'istapp',
           'frusen', 'kall', 'blåst', 'vind'],
    'lava': ['lava', 'magma', 'vulkan', 'glöd', 'hetta', 'aska', 'brinnande',
             'eld', 'flamma', 'sveda', 'kol'],
    'grotta': ['grotta', 'tunnel', 'håla', 'underjord', 'sten', 'klippa',
               'gruva', 'kaverna', 'mörker', 'djup', 'valv'],
    'vatten': ['vatten', 'river', 'sea', 'lake', 'rain', 'regn', 'bäck', 'fors',
               'vattenfall', 'ström', 'bro', 'korsning'],
    'hav': ['hav', 'sjö', 'våg', 'strand', 'kust', 'djup', 'skepp', 'båt',
            'segel', 'hamn', 'pir'],
    'slott': ['slott', 'borg', 'torn', 'mur', 'fästning', 'ruin', 'tron',
              'port', 'vallgrav', 'banér'],
    'grav': ['grav', 'kyrkogård', 'krypta', 'gravkammare', 'ben', 'skelett',
             'spöke', 'vålnad', 'död', 'kista'],
    'stad': ['stad', 'by', 'torg', 'gata', 'hus', 'värdshus', 'marknad', 'gränd',
             'butik', 'smed', 'tempel', 'kyrka'],
    'berg': ['berg', 'topp', 'klättra', 'dal', 'pass', 'höjd', 'utsikt', 'stup',
             'mountain', 'cliff', 'peak', 'cave', 'klippa'],
    'träsk': ['träsk', 'mosse', 'sump', 'gyttja', 'dimma', 'kärr', 'vass',
              'sank', 'lerig'],
}

MAX_ART_PER_REPLY = 1

# ═══════════════════════════════════════════════════════════
# FÖRGENERERAD ART-BANK (fallback när LLM returnerar tomt)
# Varje miljö har 2-3 varianter — väljs slumpmässigt.
# ═══════════════════════════════════════════════════════════
ART_BANK = {
    'skog': [
        r"""    /\      /\
   /##\    /##\
  /####\  /####\
 /######\/######\
/####|##;##|#####\
\####|..:..|####/
 \###|:::.:|###/
  \##|.;:.;|##/
   \#|..:..|#/
    \|.;::.;|/
     ^~**~^""",
        r"""  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
    |  |    |  |
 .  :  .  :  .  :
:  .  :  .  :  .
 .  :  .  :  .  :""",
    ],
    'grotta': [
        r"""  ___________________________
 /  .  :  .  :  .  :  .  :  \
|  :  .  :  .  :  .  :  .  : |
| .  :  .  :  .  :  .  :  .  |
|  :  .  :  .  :  .  :  .  : |
| .  :  .  :  .  :  .  :  .  |
|_____________________________|
  \  .  :  .  :  .  :  .  /
   \_____________________/""",
        r"""    /|  |\    /|  |\
   / |  | \  / |  | \
  /  |  |  \/  |  |  \
 /   |  |   \  |  |   \
/    |  |    \ |  |    \
\    |  |    / |  |    /
 \   |  |   /  |  |   /
  \  |  |  /   |  |  /
   \_|__|_/    |__|_/
  .  :  .  :  .  :  .""",
    ],
    'strid': [
        r"""      /\    /\
     /  \  /  \
    / /\ \/ /\ \
   / /  \  /  \ \
  / /    \/    \ \
 / /    /\    \ \
/ /    /  \    \ \
\/    / /\ \    \/
     / /  \ \
    / /    \ \
   /_/      \_\
  .  :  .  :  .""",
        r"""    |  /\  /\  |
    | /  \/  \ |
    |/ /\  /\ \|
    | /  \/  \ |
    |/ /\  /\ \|
    | /  \/  \ |
    |/    /\   |
    |    /  \  |
    |   / /\ \ |
    |  / /  \ \|
    |_/ /    \_|
   .  :  .  :  .""",
    ],
    'vila': [
        r"""       .  *  .  *  .
    *    .    *    .
  .    *    .    *
       .  *  .
    *    .    *
         |
        /|\
       / | \
      /  |  \
     /___|___\
    .  :  .  :  .
   :  .  :  .  :""",
        r"""  *  .  *  .  *  .
    .  *  .  *  .
  *  .  *  .  *
       |
      /|\
     / | \
    /  |  \
   /   |   \
  /____|____\
  .  :  .  :  .
 :  .  :  .  :
.  :  .  :  .""",
    ],
    'upptäckt': [
        r"""    ___________
   /           \
  /  *  .  *  . \
 |  .  *  .  *  |
 |  *  .  *  .  |
 |  .  *  .  *  |
  \  *  .  *  ./
   \___________/
    |  |   |  |
    |  |   |  |
   _|__|___|__|_
  /_____________\
  .  :  .  :  .""",
        r"""      .  *  .
    *  .  *  .
   ___________
  /  *  .  *  \
 |  .  *  .  * |
 |  *  .  *  . |
  \  .  *  .  /
   \_________/
    |  | |  |
   _|__|_|__|_
  /___________\
  :  .  :  .  :""",
    ],
    'is': [
        r"""    /\    /\    /\
   /  \  /  \  /  \
  / /\ \/ /\ \/ /\ \
 / /  \  /  \  /  \ \
/ /    \/    \/    \ \
\/    /\    /\    /\  \
     /  \  /  \  /  \
    / /\ \/ /\ \/ /\ \
   / /  \  /  \  /  \ \
  / /    \/    \/    \ \
 .  :  .  :  .  :  .
:  .  :  .  :  .  :""",
        r"""  *  .  *  .  *  .
    .  *  .  *  .
  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
 .  :  .  :  .  :
:  .  :  .  :  .""",
    ],
    'lava': [
        r"""  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
 .  :  .  :  .  :
:  .  :  .  :  .
 .  :  .  :  .  :
:  .  :  .  :  .
 .  :  .  :  .  :""",
        r"""    /|  |\    /|  |\
   / |  | \  / |  | \
  /  |  |  \/  |  |  \
 /   |  |   \  |  |   \
/    |  |    \ |  |    \
\    |  |    / |  |    /
 \   |  |   /  |  |   /
  \  |  |  /   |  |  /
   \_|__|_/    |__|_/
  .  :  .  :  .  :  .""",
    ],
    'vatten': [
        r"""  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
~  ~  ~  ~  ~  ~
 .  :  .  :  .  :
:  .  :  .  :  .""",
        r"""    /|    |\    /|
   / |    | \  / |
  /  |    |  \/  |
 /   |    |   \  |
/    |    |    \ |
\    |    |    / |
 \   |    |   /  |
  \  |    |  /   |
   \_|    |_/    |
  ~  ~  ~  ~  ~  ~""",
    ],
    'hav': [
        r"""  ~  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~  ~
~  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~  ~
  ~  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~  ~
~  ~  ~  ~  ~  ~  ~
 .  :  .  :  .  :  .
:  .  :  .  :  .  :""",
        r"""    /|    |\    /|
   / |    | \  / |
  /  |    |  \/  |
 /   |    |   \  |
/    |    |    \ |
\    |    |    / |
 \   |    |   /  |
  \  |    |  /   |
   \_|    |_/    |
  ~  ~  ~  ~  ~  ~""",
    ],
    'slott': [
        r"""    |  |  |  |  |
    |  |  |  |  |
   _|__|__|__|__|_
  /               \
 /  |  |  |  |  |  \
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|__|__|__|__|__|__|
 .  :  .  :  .  :  .
:  .  :  .  :  .  :""",
        r"""  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
    |  |    |  |
   _|__|____|__|_
  /              \
 /  |  |  |  |  | \
|  |  |  |  |  |  |
|__|__|__|__|__|__|""",
    ],
    'grav': [
        r"""    |  |  |  |  |
    |  |  |  |  |
   _|__|__|__|__|_
  /               \
 /  .  :  .  :  .  \
|  :  .  :  .  :  . |
| .  :  .  :  .  :  |
|  :  .  :  .  :  . |
|___________________|
  .  :  .  :  .  :
 :  .  :  .  :  .""",
        r"""  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
 .  :  .  :  .  :
:  .  :  .  :  .
 .  :  .  :  .  :
:  .  :  .  :  .""",
    ],
    'stad': [
        r"""  /\  /\  /\  /\  /\
 /  \/  \/  \/  \/  \
/ /\  /\  /\  /\  /\ \
\/  \/  \/  \/  \/  \/
 |  |  |  |  |  |  |
 |  |  |  |  |  |  |
_|__|__|__|__|__|__|_
 .  :  .  :  .  :  .
:  .  :  .  :  .  :""",
        r"""    |  |  |  |  |
    |  |  |  |  |
   _|__|__|__|__|_
  /               \
 /  |  |  |  |  |  \
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|__|__|__|__|__|__|
 .  :  .  :  .  :  .""",
    ],
    'berg': [
        r"""        /\
       /  \
      / /\ \
     / /  \ \
    / / /\ \ \
   / / /  \ \ \
  / / / /\ \ \ \
 / / / /  \ \ \ \
/ / / / /\ \ \ \ \
\/ / / /  \ \ \ \ \/
  \/ / /\ \ \ \/
    \/ /  \ \/
      \/  \/
  .  :  .  :  .""",
        r"""      /\
     /  \
    / /\ \
   / /  \ \
  / / /\ \ \
 / / /  \ \ \
/ / / /\ \ \ \
\/ / /  \ \ \ \/
  \/ /\ \ \/
    \/  \/
 .  :  .  :  .
:  .  :  .  :""",
    ],
    'träsk': [
        r"""  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
  ~  ~  ~  ~  ~  ~
 ~  ~  ~  ~  ~  ~
  .  :  .  :  .  :
 :  .  :  .  :  .
.  :  .  :  .  :""",
        r"""    /|  |\    /|  |\
   / |  | \  / |  | \
  /  |  |  \/  |  |  \
 /   |  |   \  |  |   \
/    |  |    \ |  |    \
\    |  |    / |  |    /
 \   |  |   /  |  |   /
  \  |  |  /   |  |  /
   \_|__|_/    |__|_/
  ~  ~  ~  ~  ~  ~  ~""",
    ],
    'död': [
        r"""    .  :  .  :  .
   :  .  :  .  :
  .  :  .  :  .
   :  .  :  .  :
    .  :  .  :  .
   :  .  :  .  :
  .  :  .  :  .
   :  .  :  .  :
    .  :  .  :  .""",
        r"""  /\    /\    /\
 /  \  /  \  /  \
/ /\ \/ /\ \/ /\ \
\/  \  /  \  /  \/
    |  |    |  |
 .  :  .  :  .  :
:  .  :  .  :  .
 .  :  .  :  .  :""",
    ],
}

# ── Event-triggered art (från mekaniska effekter) ──
EVENT_ART = {
    'level_up': 'Rita en triumferande ljuspelare som bryter genom mörkret, strålar som sprider sig uppåt, gnistor och energi som strålar ut.',
    'npc_död': 'Rita en ensam gravsten med ett kors, dött gräs runt den, och en kråka som sitter på toppen.',
    'ny_dag': 'Rita en soluppgång över mörka kullar, strålar som bryter horisonten, fåglar som silhuetter mot himlen.',
    'quest': 'Rita en utrullad pergamentrulle med ett vaxsigill, banerband, och en fjäderpenna som vilar bredvid.',
}

EVENT_ART_BANK = {
    'level_up': r"""       *  .  *
    .  *  .  *  .
  *  .  *  .  *  .
       |
       |
       |
       |
       |
  _____|_____
 /           \
/_____________\
 .  :  .  :  .""",
    'npc_död': r"""    |
    |
   _|_
  /   \
 /     \
|       |
|       |
|       |
|_______|
 .  :  .  :  .
:  .  :  .  :""",
    'ny_dag': r"""  *  .  *  .  *
    .  *  .  *
  *  .  *  .  *
       |
      /|\
     / | \
    /  |  \
   /   |   \
  /____|____\
 .  :  .  :  .
:  .  :  .  :""",
    'quest': r"""  ___________
 /           \
/  .  :  .  : \
|  :  .  :  . |
| .  :  .  :  |
|  :  .  :  . |
 \  .  :  .  /
  \_________/
   |  | |  |
  _|__|_|__|_
 /___________\
  :  .  :  .""",
}

# Event-typ → CSS-klassnamn för frontend
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


def get_fallback_art(environment: str) -> str | None:
    """Hämta förgenererad ASCII-art från banken (slumpmässig variant)."""
    variants = ART_BANK.get(environment)
    if not variants:
        return None
    return random.choice(variants)


def get_fallback_event_art(event_type: str) -> str | None:
    """Hämta förgenererad event-art från banken."""
    return EVENT_ART_BANK.get(event_type)


def build_art_prompt(environment: str) -> str:
    """Bygg prompt för ambient ASCII-art generering (svenska, med few-shot)."""
    desc_map = {
        'skog': 'Rita en mörk, tät skog med vridna träd, dimma mellan stammarna, och ett svagt sken från något dolt.',
        'is': 'Rita ett fruset landskap med taggiga isformationer, drivande snö, och en blek kall måne lågt på himlen.',
        'lava': 'Rita ett vulkaniskt helvete med floder av lava, gnistor, och svarta klippor mot ett orange sken.',
        'grotta': 'Rita en djup grotta med stalaktiter som droppar, trånga passager, och något som lyser svagt i mörkret.',
        'vatten': 'Rita en dimmig flod som slingrar sig genom mörka klippor, regn som faller, och en svag reflektion på vattenytan.',
        'hav': 'Rita ett mörkt hav med vågor som slår mot en öde strand, och åskmoln som samlas vid horisonten.',
        'slott': 'Rita ett sönderfallande slott med trasiga torn, murgröna på väggarna, och ett enda upplyst fönster högt upp.',
        'grav': 'Rita en hemsökt kyrkogård med sneda gravstenar, döda träd, och dimma som stiger från den kalla marken.',
        'stad': 'Rita en medeltida stadsgata i skymningen med sneda hus, en hängande skylt, och våt kullersten som reflekterar fackelsken.',
        'berg': 'Rita en bergstopp ovanför molnen med en smal klippstig, vindpinad och svindlande, med en hök som kretsar.',
        'träsk': 'Rita en dimmig sumpmark med vass, grumligt vatten, irrbloss, och knotiga döda träd som sträcker sig uppåt.',
        'strid': 'Rita en kaotisk stridsscen med korsade svärd, flygande pilar, stänkande blod, och en fallen sköld på marken.',
        'död': 'Rita en dödsscen: en dödskalle, utspridda ben, ett utsläckt ljus, och mörker som sluter sig från alla håll.',
        'vila': 'Rita en lägereld på natten med gnistor som stiger mot mörkret, en tält-siluett, och stjärnor ovanför.',
        'upptäckt': 'Rita en gömd skatt: en öppen kista som lyser, utspridda mynt, och en hemlig dörr på glänt med gyllene ljus.',
    }
    desc = desc_map.get(environment, f'Rita en stämningsfull scen av: {environment}.')

    fewshot = get_fallback_art(environment) or get_fallback_art('skog')

    return (
        "Du är en ASCII-konstnär för ett fantasy-rollspel. "
        "Skapa en stämningsfull scen med tecken.\n\n"
        f"{desc} Max 12 rader, 50 tecken brett.\n\n"
        "KRITISKA REGLER:\n"
        "- Använd ENDAST dessa tecken: / \\ | - _ . : ; # @ * ^ ~ + =\n"
        "- INGA bokstäver, INGA ord, INGA etiketter\n"
        "- INGA markdown-stängsel, INGA förklaringar\n"
        "- Svara ENDAST med ASCII-konsten, inget annat\n\n"
        f"EXEMPEL PÅ BRA ASCII-ART (följ denna stil):\n{fewshot}\n\n"
        "Skapa nu en liknande scen."
    )


def build_event_art_prompt(event_type: str) -> str | None:
    """Bygg prompt för event-triggered ASCII-art."""
    desc = EVENT_ART.get(event_type)
    if not desc:
        return None
    fewshot = get_fallback_event_art(event_type) or ""
    return (
        "Du är en ASCII-konstnär för ett fantasy-rollspel. "
        "Skapa en liten, slagkraftig ASCII-art-scen.\n\n"
        f"{desc} Max 8 rader, 40 tecken brett.\n\n"
        "KRITISKA REGLER:\n"
        "- Använd ENDAST dessa tecken: / \\ | - _ . : ; # @ * ^ ~ + =\n"
        "- INGA bokstäver, INGA ord, INGA etiketter\n"
        "- INGA markdown-stängsel, INGA förklaringar\n"
        "- Svara ENDAST med ASCII-konsten, inget annat\n\n"
        f"EXEMPEL:\n{fewshot}\n\n"
        "Skapa nu en liknande scen."
    )


def should_generate_art(meta: dict, turn_count: int) -> bool:
    """Cooldown: max 1 art per ART_COOLDOWN meddelanden."""
    last = meta.get('last_art_turn', -ART_COOLDOWN)
    return (turn_count - last) >= ART_COOLDOWN


def postprocess_art(raw: str) -> str | None:
    """
    Kvalitetskontroll av LLM-genererad ASCII-art.
    - Ta bort rader längre än 60 tecken
    - Ta bort rader som mestadels är bokstäver (men tillåt enstaka)
    - Max 14 rader
    - Släng om < 3 rader kvar
    """
    if not raw:
        return None

    art = raw.strip()
    if art.startswith("```"):
        art = re.sub(r"^```[a-z]*\n?", "", art)
        art = re.sub(r"\n?```$", "", art)
        art = art.strip()

    lines = art.split('\n')
    cleaned = []
    for line in lines:
        if len(line) > 60:
            continue
        alpha_count = sum(1 for c in line if c.isalpha())
        non_space = sum(1 for c in line if not c.isspace())
        if non_space > 0 and alpha_count / non_space > 0.5:
            continue
        cleaned.append(line.rstrip())

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    cleaned = cleaned[:14]

    if len(cleaned) < 3:
        return None

    return '\n'.join(cleaned)
