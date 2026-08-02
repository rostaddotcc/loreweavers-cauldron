"""
The Lore Weaver's Cauldron — Tärningsmotor
===============================
Parserar notation som '1d20+4', '2d6-1', '1d20'.
"""

import random
import re


def roll(notation: str) -> dict:
    """
    Kasta tärningar. Stödjer: NdX+M, NdX-M, NdX.
    Returnerar {rolls, total, crit, fail, notation}.
    """
    notation = notation.strip().lower().replace(" ", "")
    m = re.match(r"^(\d+)d(\d+)([+-]\d+)?$", notation)
    if not m:
        raise ValueError(f"Ogiltig tärningsnotation: {notation}")

    count = int(m.group(1))
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0

    if count < 1 or count > 100:
        raise ValueError("Antal tärningar måste vara 1–100")
    if sides < 2 or sides > 1000:
        raise ValueError("Tärningssidor måste vara 2–1000")

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier

    # Crit/fail bara för enskilda d20-kast
    crit = count == 1 and sides == 20 and rolls[0] == 20
    fail = count == 1 and sides == 20 and rolls[0] == 1

    return {
        "notation": notation,
        "rolls": rolls,
        "modifier": modifier,
        "total": total,
        "crit": crit,
        "fail": fail,
    }
