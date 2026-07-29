"""
Mörkrets Rike — Platser & Resor
================================
Hanterar besökta platser, sevärdheter, och restider.
Kartan är helt dynamisk — inga hårdkodade platser. Nya platser placeras
deterministiskt (seedat från kampanj-ID + platsnamn) så att samma plats
alltid hamnar på samma koordinat inom en kampanj.
"""

import hashlib
import math

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
            'terrain': loc.get('terrain', 'okänd'),
            'x': loc.get('x', 50),
            'y': loc.get('y', 50),
            'visited': name in visited or name == current_name,
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
