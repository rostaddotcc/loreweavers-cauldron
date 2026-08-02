"""
The Lore Weaver's Cauldron — Platser & Resor
================================
Hanterar besökta platser, sevärdheter, och restider.
Kartan är helt dynamisk — inga hårdkodade platser. Nya platser placeras
deterministiskt (seedat från kampanj-ID + platsnamn) så att samma plats
alltid hamnar på samma koordinat inom en kampanj.
"""

import hashlib
import math
import re

# Terräng-modifierare (dagar per "enhet" avstånd)
TERRAIN = {
    'väg': 0.5,       # Halv dag per enhet — bra vägar
    'stig': 0.8,      # Små stigar
    'skog': 1.2,      # Tät skog, långsamt
    'berg': 1.8,      # Bergigt, mycket långsamt
    'träsk': 1.5,     # Sumpigt, svårt
    'slätt': 0.6,     # Öppen mark
    'is': 1.4,        # Fruset, halt
    'hav': 0.4,       # Båt — snabbt
    'okänd': 1.0,     # Default
}

# Terräng-typer som kan tilldelas nya platser (viktad lista)
TERRAIN_POOL = ['skog', 'skog', 'skog', 'slätt', 'slätt', 'väg', 'stig',
                'berg', 'träsk', 'is', 'hav']


def place_location(name: str, campaign_id: str = "") -> dict:
    """Deterministisk placering av en ny plats.

    Hashar (kampanj-ID + platsnamn) → x,y i [8,92] + terräng.
    Samma namn i samma kampanj ger ALLTID samma koordinat, oavsett
    i vilken ordning platser upptäcks. Inga hårdkodade platser.
    """
    seed = hashlib.md5(f"{campaign_id}:{name.lower().strip()}".encode()).hexdigest()
    # Två oberoende koordinater + terräng ur hashen
    x = 8 + (int(seed[0:8], 16) % 85)
    y = 8 + (int(seed[8:16], 16) % 85)
    terrain = TERRAIN_POOL[int(seed[16:24], 16) % len(TERRAIN_POOL)]
    return {'x': x, 'y': y, 'terrain': terrain}


def clean_location_name(name: str) -> str:
    """Städa platsnamn — DM:er och LLM:er ibland skickar hela stycken.

    Regler:
    - Klipp vid första em-dash (—) eller punkt följt av mellanslag + stor bokstav
    - Klipp vid första kommatecken om namnet är > 40 tecken (beskrivning följer)
    - Max 60 tecken
    - Ta bort avslutande skiljetecken
    """
    name = name.strip()
    if not name:
        return name

    # Klipp vid em-dash (beskrivning följer)
    for sep in (' — ', ' – ', ' - '):
        idx = name.find(sep)
        if idx > 3:  # behåll minst 3 tecken före
            name = name[:idx]
            break

    # Klipp vid ". " följt av stor bokstav (ny mening = beskrivning)
    import re
    m = re.search(r'\.\s+[A-ZÅÄÖ]', name)
    if m and m.start() > 3:
        name = name[:m.start() + 1]

    # Klipp vid kommatecken om namnet fortfarande är långt
    if len(name) > 40:
        idx = name.find(',')
        if idx > 3:
            name = name[:idx]

    # Hård gräns
    if len(name) > 60:
        name = name[:57].rstrip() + '…'

    return name.rstrip(' .,;:—–-')


# ═══════════════════════════════════════
# Platsnamn-dedup (2026-08-02)
# Guardian/DM kan ge samma plats olika namn över turer ("The X" vs "X",
# "X, kvalificerare", "The X's Y" vs "The Y"). Exakt-sträng-jämförelse räcker
# inte — dessa hjälpfunktioner normaliserar och matchar nära-duplikat.
# ═══════════════════════════════════════

_POSS_RE = re.compile(r"^[a-zåäö'’]+\s+(.+)$")


def location_key(name: str) -> str:
    """Normalisera ett platsnamn till en dedup-nyckel.

    - clean_location_name (klipp vid em-dash/punkt/komma, max 60 tecken)
    - lowercase + kollapsa whitespace
    - ta bort inledande 'the '
    - ta bort parenteser ('(Mid-Ring Docks)' → '')
    - klipp vid kommatecken OM huvudet är >= 4 tecken (annars behålls hela,
      så 'Halcyra, the Lantern City' → 'halcyra' — container-namnet)
    """
    n = clean_location_name(name).strip().lower()
    n = re.sub(r'\s+', ' ', n)
    n = re.sub(r'^the\s+', '', n)
    n = re.sub(r'\s*\([^)]*\)\s*', ' ', n).strip()
    if ',' in n and len(n.split(',')[0].strip()) >= 4:
        n = n.split(',')[0].strip()
    return n


def locations_match(a: str, b: str) -> bool:
    """True om två platsnamn refererar till SAMMA plats.

    Regler (medvetet konservativa — slå ALDRIG ihop genuint olika platser):
    - nyckel-likhet ('the hollow forge' == 'hollow forge')
    - prefix >= 5 tecken + mellanslagsgräns ('upper rings' ⊂ 'upper rings of halcyra')
    - possessiv: "forge's speaking chamber" ~ 'speaking chamber'
    Skyddar mot falska matchningar: 'halcyra' vs 'upper rings of halcyra'
    (container vs del) och korta generiska ord (< 5 tecken).
    """
    ka, kb = location_key(a), location_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if len(short) < 5:
        return False
    if long_.startswith(short) and (len(long_) == len(short) or long_[len(short)] == ' '):
        return True
    m = _POSS_RE.match(long_)
    return bool(m and m.group(1) == short)


def find_location(locs: list, name: str):
    """Hitta befintlig plats i listan som matchar namnet (fuzzy).

    Returnerar (index, plats-objekt) eller (None, None).
    """
    for i, l in enumerate(locs):
        if isinstance(l, dict) and locations_match(str(l.get('name', '')), name):
            return i, l
    return None, None


def calculate_travel_days(from_loc: dict, to_loc: dict) -> float:
    """Beräkna restid i dagar mellan två platser."""
    dx = to_loc.get('x', 50) - from_loc.get('x', 50)
    dy = to_loc.get('y', 50) - from_loc.get('y', 50)
    distance = math.sqrt(dx * dx + dy * dy)

    # Terrängmodifierare baserat på destinationens terräng
    terrain = to_loc.get('terrain', 'okänd')
    modifier = TERRAIN.get(terrain, 1.0)

    # Skala: ~10 enheter = 1 dags resa på väg
    days = (distance / 10.0) * modifier
    return max(0.5, round(days, 1))  # Minst en halv dag


def format_travel_time(days: float) -> str:
    """Formatera restid som läsbar text."""
    if days < 0.5:
        return 'Här är du'
    elif days < 1:
        return 'Mindre än en dag'
    elif days == 1:
        return '1 dags resa'
    elif days < 2:
        return f'{days:.1f} dagars resa'
    else:
        return f'{days:.0f} dagars resa'


def get_locations_with_travel(state: dict) -> list[dict]:
    """
    Returnera alla kända platser med restid från nuvarande plats.
    Används av /api/campaign/locations endpointen.
    Helt dynamisk — bara platser som kampanjen själv upptäckt.
    """
    world = state.get('world', {})
    current_name = world.get('current_location', '')
    visited = world.get('visited_locations', [])
    campaign_id = state.get('meta', {}).get('campaign_id', '')

    all_locations = {}

    # visited_locations kan innehålla STRÄNGAR (från [PLATS:]-taggen) ELLER
    # dict-objekt (från Guardian locations_new) — normalisera till namn-set
    # så "visited"-flaggan funkar för båda. (fix 2026-08-01: Guardian-platser
    # visades som dimmade ◇ istället för besökta ◆ pins)
    visited_names = {
        v.strip().lower() if isinstance(v, str) else str(v.get('name', '')).strip().lower()
        for v in visited
    }

    # Bara kampanjens egna platser (inga defaults)
    for loc in state.get('locations', []):
        name = loc.get('name', '')
        if not name:
            continue
        # Platser utan koordinater (t.ex. från world-build) placeras nu
        if 'x' not in loc or 'y' not in loc:
            placed = place_location(name, campaign_id)
            loc['x'], loc['y'] = placed['x'], placed['y']
            if loc.get('terrain', 'okänd') == 'okänd':
                loc['terrain'] = placed['terrain']
        all_locations[name] = {
            'name': name,
            'description': loc.get('description', ''),
            'lore': loc.get('lore', ''),
            'terrain': loc.get('terrain', 'okänd'),
            'x': loc.get('x', 50),
            'y': loc.get('y', 50),
            'visited': name.strip().lower() in visited_names or name == current_name,
            'current': name == current_name,
            'landmarks': loc.get('landmarks', []),
        }

    # Beräkna restider från nuvarande plats
    current_loc = all_locations.get(current_name, {'x': 50, 'y': 50})
    result = []
    for name, loc in all_locations.items():
        travel_days = calculate_travel_days(current_loc, loc)
        loc['travel_days'] = travel_days
        loc['travel_text'] = format_travel_time(travel_days) if not loc['current'] else 'Du är här'
        result.append(loc)

    # Sortera: nuvarande först, sedan efter restid
    result.sort(key=lambda l: (not l['current'], l['travel_days']))
    return result
