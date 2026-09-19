"""
The Lore Weaver's Cauldron — Atmosfär-cooldown
===================================
Historik: ASCII-art flyttades till Guardian (commit 044c6c5) —
atmosfär-subagentens art-bank, prompts och postprocess är borta sedan dess.
Kvar lever endast cooldown-räknaren som main.py rådgör med innan
Guardian får generera art. Full modulhistorik: git log -- backend/atmosphere.py
"""

# ── Cooldown: max 1 art per ART_COOLDOWN meddelanden ──
ART_COOLDOWN = 2


def should_generate_art(meta: dict, turn_count: int) -> bool:
    """Cooldown: max 1 art per ART_COOLDOWN meddelanden."""
    last = meta.get('last_art_turn', -ART_COOLDOWN)
    return (turn_count - last) >= ART_COOLDOWN
