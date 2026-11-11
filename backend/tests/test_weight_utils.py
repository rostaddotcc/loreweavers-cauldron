"""Tester för weight_utils.compute_carry_weight (single source of truth).

Täcker: items+coins-summa, qty-multiplikation, 50-mynt-per-lb-konventionen,
tom/saknad state-tolerans, trasiga värden, pct-beräkning (inkl. max=0 → None).
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from weight_utils import compute_carry_weight  # noqa: E402


def test_items_plus_coins_sum():
    state = {
        "character": {"max_weight_lbs": 150},
        "inventory": [
            {"name": "Svärd", "weight": 3.0, "qty": 1},
            {"name": "Läkedryck", "weight": 0.5, "qty": 4},
        ],
        "currency": {"pp": 0, "gp": 100, "sp": 50, "cp": 50},
    }
    w = compute_carry_weight(state)
    assert w["items_lbs"] == 5.0        # 3.0 + 4×0.5
    assert w["coins_lbs"] == 4.0        # 200 mynt / 50
    assert w["total"] == 9.0
    assert w["max"] == 150.0
    assert w["pct"] == 6                # 9/150 = 6 %


def test_empty_state_tolerance():
    w = compute_carry_weight({})
    assert w == {"items_lbs": 0.0, "coins_lbs": 0.0, "total": 0.0, "max": 0.0, "pct": None}


def test_missing_keys_and_junk_values():
    state = {
        "character": {"max_weight_lbs": "120"},   # str ska tolereras
        "inventory": [
            {"name": "OK", "weight": 2, "qty": 3},
            {"name": "Ingen vikt"},               # saknar weight/qty → 0
            {"name": "Trasig", "weight": "x", "qty": 1},  # skräp → skip
            "inte-en-dict",                        # skräp → skip
            None,
        ],
        "currency": {"gp": "10", "sp": None, "cp": 5},
    }
    w = compute_carry_weight(state)
    assert w["items_lbs"] == 6.0
    assert w["coins_lbs"] == 0.3        # 15 mynt / 50
    assert w["total"] == 6.3
    assert w["max"] == 120.0
    assert w["pct"] == 5


def test_zero_max_gives_none_pct():
    state = {
        "character": {},
        "inventory": [{"weight": 10, "qty": 1}],
        "currency": {"gp": 50},
    }
    w = compute_carry_weight(state)
    assert w["total"] == 11.0
    assert w["max"] == 0.0
    assert w["pct"] is None


def test_none_state_no_crash():
    w = compute_carry_weight(None)
    assert w["total"] == 0.0 and w["pct"] is None
