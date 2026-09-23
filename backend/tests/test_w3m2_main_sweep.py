"""W3-M2: main.py small sweep — bärvikt via weight_utils, price_gp-passthrough,
WAN 403-ärlighet, promo_bonus_legacy-flagga.

Ingen riktig data rörs: users.json + ledgers pekas mot tmp.
"""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import main  # noqa: E402
from weight_utils import compute_carry_weight  # noqa: E402


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def turn_ledgers_dir(tmp_path, monkeypatch):
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d


# ── Task 1: Bärvikt i DM truth block via weight_utils ─────────────────────

def _carry_line(state):
    text = main.compact_state(state)
    return next(l for l in text.splitlines() if l.startswith("Bärvikt:"))


def test_truth_block_carry_matches_weight_utils():
    state = {
        "character": {"name": "Test", "class": "Krigare", "level": 1,
                      "hp": {"current": 10, "max": 10}, "ac": 16,
                      "max_weight_lbs": 150.0},
        "currency": {"pp": 0, "gp": 2000, "sp": 0, "cp": 0},
        "inventory": [{"name": "Svärd", "weight": 3.0, "qty": 2, "equipped": True},
                      {"name": "Rep", "weight": 10.0, "qty": 1}],
    }
    carry = compute_carry_weight(state)
    line = _carry_line(state)
    # items 16 lb + mynt 2000/50 = 40 lb → 56.0 / 150 lb (37%)
    assert carry["total"] == 56.0 and carry["max"] == 150.0 and carry["pct"] == 37
    assert line == f"Bärvikt: {carry['total']:.1f} / {carry['max']:.0f} lb ({carry['pct']}%)"
    assert line == "Bärvikt: 56.0 / 150 lb (37%)"


def test_truth_block_carry_no_max():
    state = {
        "character": {"name": "Test", "class": "Krigare", "level": 1,
                      "hp": {"current": 10, "max": 10}, "ac": 16},
        "currency": {"pp": 0, "gp": 50, "sp": 0, "cp": 0},
        "inventory": [{"name": "Yxa", "weight": 4.0, "qty": 1}],
    }
    # 4 lb items + 1 lb mynt = 5.0, ingen max → kort form
    assert _carry_line(state) == "Bärvikt: 5.0 lb"


# ── Task 2: price_gp-passthrough ──────────────────────────────────────────

def test_keep_unknown_item_keys_preserves_price_gp():
    norm = main._normalize_item({"name": "Svärd", "type": "Vapen"})
    raw = {"name": "Svärd", "type": "Vapen", "price_gp": 15, "empty": None, "blank": ""}
    main._keep_unknown_item_keys(norm, raw)
    assert norm["price_gp"] == 15
    assert "empty" not in norm and "blank" not in norm
    # normaliserade fält skrivs aldrig över
    assert norm["weight"] == 1.0 and norm["qty"] == 1


def test_keep_unknown_item_keys_never_overrides_schema():
    norm = main._normalize_item({"name": "Svärd", "qty": 3})
    main._keep_unknown_item_keys(norm, {"name": "Fusk", "qty": 999, "weight": 42.0})
    assert norm["name"] == "Svärd" and norm["qty"] == 3 and norm["weight"] == 1.0


def test_finalize_character_data_keeps_price_gp():
    char_data = {
        "name": "Merrick", "class": "Krigare",
        "inventory": [{"name": "Långsvärd", "type": "Vapen", "qty": 1,
                       "weight": 3.0, "price_gp": 15}],
    }
    out, clean, had_inv = main._finalize_character_data(char_data, lang="sv")
    assert had_inv and len(clean) == 1
    assert clean[0]["price_gp"] == 15


def test_patch_inventory_keeps_price_gp():
    # PATCH /api/campaign/inventory-vägen kör _normalize_item +
    # _keep_unknown_item_keys (main.py ~:7730) — samma kontrakt som char-gen.
    raw = {"name": "Sköld", "type": "Rustning", "price_gp": 10}
    norm = main._normalize_item(raw)
    main._keep_unknown_item_keys(norm, raw)
    assert norm["price_gp"] == 10
    assert norm["category"] == "armor" and norm["weight"] == 1.0


# ── Task 3: WAN 403 säger daily image cap, inte turns ─────────────────────

def test_wan_quota_403_says_image_cap(users_file):
    users = {"bob": {"password_hash": "x", "salt": "y", "role": "player",
                     "wan_used_today": main.WAN_DAILY_LIMIT,
                     "wan_reset_date": main._today_str(),
                     "turns_used": 0, "turn_cap": 50, "reset_date": main._today_str()}}
    users_file.write_text(__import__("json").dumps(users))
    with pytest.raises(HTTPException) as ei:
        main._consume_wan_quota("bob")
    assert ei.value.status_code == 403
    detail = ei.value.detail
    msg = detail if isinstance(detail, str) else detail.get("message", "")
    assert "image" in msg.lower()
    assert "daily image cap" in msg.lower()
    # ärlig text: särskiljer kvot från turn-saldo
    assert "not your turn balance" in msg.lower()


# ── Task 5: promo_bonus_legacy i _user_free_info + /api/me-shape ──────────

def test_user_free_info_promo_legacy_flag(users_file):
    users = {"carol": {"password_hash": "x", "salt": "y", "role": "player",
                       "promo_bonus": 300, "turns_used": 0, "turn_cap": 50,
                       "reset_date": main._today_str()}}
    users_file.write_text(__import__("json").dumps(users))
    info = main._user_free_info("carol")
    assert info["promo_bonus"] == 300
    assert info["promo_bonus_legacy"] is True

    users["carol"]["promo_bonus"] = 0
    users_file.write_text(__import__("json").dumps(users))
    info = main._user_free_info("carol")
    assert info["promo_bonus"] == 0
    assert info["promo_bonus_legacy"] is False
