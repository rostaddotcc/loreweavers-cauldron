"""
Mörkrets Rike — Platser & Resor
================================
Hanterar besökta platser, sevärdheter, och restider.
"""

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

# Standardplatser med koordinater (enkel 2D-karta, 0-100 skala)
# DM:n kan lägga till nya via [PLATS:...] — koordinater sätts automatiskt
DEFAULT_LOCATIONS = {
    'Gråvakt': {'x': 50, 'y': 50, 'terrain': 'väg', 'description': 'En liten handelsstad vid korsningen av två vägar.'},
    'Askans Dal': {'x': 35, 'y': 40, 'terrain': 'skog', 'description': 'En dimmig dal där askan aldrig slutar falla.'},
    'Den Övergivna Kvarnen': {'x': 30, 'y': 35, 'terrain': 'skog', 'description': 'En ruttnande kvarn med ett grönt ljus i källaren.'},
    'Sista Glöden': {'x': 52, 'y': 48, 'terrain': 'väg', 'description': 'Värdshuset där alla historier börjar och slutar.'},
    'Gravfältet': {'x': 25, 'y': 30, 'terrain': 'berg', 'description': 'Ett vidsträckt gravfält norr om dalen.'},
    'Väst': {'x': 15, 'y': 55, 'terrain': 'slätt', 'description': 'Byn i väster, känd för sitt bryggeri.'},
}


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
    """
    world = state.get('world', {})
    current_name = world.get('current_location', '')
    visited = world.get('visited_locations', [])

    # Samla alla platser: defaults + kampanjens egna
    all_locations = {}

    # Lägg till defaults som är besökta eller relevanta
    for name, data in DEFAULT_LOCATIONS.items():
        all_locations[name] = {
            'name': name,
            'description': data.get('description', ''),
            'terrain': data.get('terrain', 'okänd'),
            'x': data.get('x', 50),
            'y': data.get('y', 50),
            'visited': name in visited or name == current_name,
            'current': name == current_name,
            'landmarks': [],
        }

    # Lägg till kampanjens egna platser
    for loc in state.get('locations', []):
        name = loc.get('name', '')
        if not name:
            continue
        if name not in all_locations:
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
        else:
            # Uppdatera befintlig med kampanjdata
            all_locations[name]['description'] = loc.get('description', all_locations[name]['description'])
            all_locations[name]['visited'] = name in visited or name == current_name
            all_locations[name]['current'] = name == current_name

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
