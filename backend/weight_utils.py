"""weight_utils — EN beräkning av bärvikt (single source of truth).

Bakgrund (audit-mechanics.md §2): fyra divergerande viktoberäkningar finns
idag. Denna modul konsoliderar semantiken så alla konsumenter kan migreras
till en funktion. Beteendet matchar den nuvarande kod-vägen exakt:

  - föremål: float(weight or 0) × int(qty or 1)  (saknad vikt = 0 lb;
    _normalize_item i guardian.py sätter redan weight-default 1.0 vid
    INTAGNING, så beräkningen här ska inte gissa 1.0)
  - mynt: 50 mynt = 1 lb oavsett valör (5e) — samma konvention som
    main.py:575 currency_weight() och guardian.py:1874
  - max: character.max_weight_lbs (5e: STR × 15)

TODO — migrera dessa fyra anropsställen till compute_carry_weight():
  1. guardian.py:1753   (current_weight före items_add — viktkontroll)
  2. guardian.py:1871-1881 (encumbrance-beräkning, _encumbrance_level)
  3. main.py:4510-4517  (DM truth block "Bärvikt: X / Y lb (Z%)")
  4. frontend/chat.html:8400 (carry-weight-bar i karaktärsarket — JS-sida,
     exponera via API eller duplicera konstanten COINS_PER_LB medtestat)
"""
from __future__ import annotations

COINS_PER_LB = 50.0  # 5e: 50 mynt = 1 lb, oavsett valör
COIN_DENOMS = ("pp", "gp", "sp", "cp")


def compute_carry_weight(state: dict | None) -> dict:
    """Beräkna spelarens totala bärvikt ur spelstate.

    Tolerant mot saknade/trasiga nycklar (tom state → alla nollor).

    Returnerar:
        {
          "items_lbs":  float,  # summa föremål (weight × qty)
          "coins_lbs":  float,  # myntvikt (totalt antal mynt / 50)
          "total":      float,  # items + coins
          "max":        float,  # max_weight_lbs (0 = okänd/obegränsad)
          "pct":        int|None,  # procent av max (None om max <= 0)
        }
    """
    state = state if isinstance(state, dict) else {}
    char = state.get("character") or {}
    inventory = state.get("inventory") or []
    currency = state.get("currency") or {}

    items_lbs = 0.0
    if isinstance(inventory, list):
        for it in inventory:
            if not isinstance(it, dict):
                continue
            try:
                items_lbs += float(it.get("weight", 0) or 0) * int(it.get("qty", 1) or 1)
            except (TypeError, ValueError):
                continue

    coins = 0
    if isinstance(currency, dict):
        for denom in COIN_DENOMS:
            try:
                coins += int(currency.get(denom, 0) or 0)
            except (TypeError, ValueError):
                continue
    coins_lbs = round(coins / COINS_PER_LB, 2)

    try:
        max_lbs = float(char.get("max_weight_lbs", 0) or 0)
    except (TypeError, ValueError):
        max_lbs = 0.0

    total = round(items_lbs + coins_lbs, 2)
    pct = round(total / max_lbs * 100) if max_lbs > 0 else None

    return {
        "items_lbs": round(items_lbs, 2),
        "coins_lbs": coins_lbs,
        "total": total,
        "max": max_lbs,
        "pct": pct,
    }
