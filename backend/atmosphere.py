"""
Mörkrets Rike — Atmosfär-subagent
===================================
Analyserar DM-svar och genererar ASCII/CLI-art inline.
Kör på en snabb modell (qwen3.6-flash / deepseek-v4-flash).
"""

import re

# Miljöer som triggar ASCII-art
ENVIRONMENTS = {
    'skog': ['skog', 'träd', 'gran', 'björk', 'lövv', 'snår', 'glänta', 'rot', 'mossa', 'svamp'],
    'is': ['is', 'snö', 'frost', 'glaciär', 'kyla', 'vinter', 'tjäle', 'istapp'],
    'lava': ['lava', 'magma', 'vulkan', 'eld', 'glöd', 'hetta', 'aska', 'brinnande'],
    'grotta': ['grotta', 'tunnel', 'håla', 'underjord', 'sten', 'klippa', 'gruva', 'kaverna'],
    'hav': ['hav', 'sjö', 'vatten', 'våg', 'strand', 'kust', 'djup', 'ström'],
    'slott': ['slott', 'borg', 'torn', 'mur', 'fästning', 'ruin', 'valv', 'tron'],
    'grav': ['grav', 'kyrkogård', 'krypta', 'gravsten', 'död', 'ben', 'skelett', 'gravkammare'],
    'stad': ['stad', 'by', 'torg', 'gata', 'hus', 'värdshus', 'marknad', 'gränd'],
    'berg': ['berg', 'topp', 'klättra', 'dal', 'pass', 'höjd', 'utsikt', 'stup'],
    'träsk': ['träsk', 'mosse', 'sump', 'gyttja', 'dimma', 'kärr', 'vass'],
}

# Max antal ASCII-art per svar (undvik spam)
MAX_ART_PER_REPLY = 1

ATMOSPHERE_PROMPT = """Du är en ASCII-konstnär för ett mörkt fantasy-rollspel.

Skapa en kompakt ASCII-art-scen (max 12 rader, max 50 tecken bred) som visar:
{environment}

Regler:
- Använd ENBART dessa tecken: ░▒▓█▄▀■□▪▫●○◐◑◒◓◔◕◖◗◘◙◚◛◜◝◞◟◠◡◢◣◤◥◦◧◨◩◪◫◬◭◮◯◰◱◲◳◴◵◶◷◸◹◺◻◼◽◾◿★☆♠♣♥♦♪♫☼♀♂♩♬♭♮♯✓✗✘✚✛✜✝✞✟✠✡✢✣✤✥✦✧✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀❁❂❃❄❅❆❇❈❉❊❋
- Plus vanliga: . , : ; - = + * # @ % & / \ | _ ~ ^ < > ( ) [ ] { }
- Mörk, atmosfärisk, stämningsfull — tänk Elden Ring möter SNES
- Ingen text i konsten, bara bilden
- Svara ENDAST med ASCII-konsten, inget annat. Ingen markdown, inga förklaringar.
- Max 12 rader. Max 50 tecken per rad."""


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
    """Bygg prompt för ASCII-art generering."""
    env_desc = {
        'skog': 'En mörk, tät skog med höga träd, rötter och dimma mellan stammarna',
        'is': 'Ett fruset landskap med is, snö och glaciärer under en kall himmel',
        'lava': 'Eld och lava som rinner, glödande magma och aska i luften',
        'grotta': 'En mörk grotta med stalaktiter, trånga tunnlar och drypande vatten',
        'hav': 'Ett mörkt hav med vågor, en enslig strand eller ett djup',
        'slott': 'Ett förfallet slott eller en borg med torn, murar och valv',
        'grav': 'En kyrkogård, krypta eller gravkammare med ben och gravstenar',
        'stad': 'En medeltida stad med gränder, torg och värdshus i skymningen',
        'berg': 'Bergstoppar, dalar och klippor med utsikt över mörka vidder',
        'träsk': 'Ett dimmigt träsk med vass, gyttja och dunkla ljud',
    }
    return ATMOSPHERE_PROMPT.format(environment=env_desc.get(environment, environment))
