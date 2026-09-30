"""P3.1-backfillen (scripts/backfill_turn_pool.py) — planen, invarianterna och idempotensen.

Täcker:
  - opening_balance = kvar + använt − redan bokfört (aldrig ett påhittat köp)
  - grant-ledgern blir KOMPLETT framåt: granted == paid_left + paid_used_total
  - idempotens: en andra körning skriver inga nya rader
  - konton utan pott-historik rörs inte alls
  - promo är ingen grant → ingen opening_balance-rad för promo
  - ledger-rader utan hink blir turns_used_unknown_total (aldrig "free")
  - öppningsraden läses av _turn_pool som "köp okänt" (granted_known False)

Scriptet ligger i scripts/ (utanför backend-mounten) → körs med
  -v <repo>/scripts:/app/scripts:ro och DND_SCRIPTS_DIR=/app/scripts.
"""
import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
SCRIPTS_DIR = os.environ.get("DND_SCRIPTS_DIR") or str(Path(__file__).resolve().parents[2] / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import auth  # noqa: E402
import main  # noqa: E402
import backfill_turn_pool as bf  # noqa: E402

TODAY = "2026-09-28"


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    (tmp_path / "turn_ledgers").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bf, "DATA", tmp_path)
    monkeypatch.setattr(bf, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(bf, "GRANTS_FILE", tmp_path / "turn_grants.jsonl")
    monkeypatch.setattr(bf, "LEDGERS_DIR", tmp_path / "turn_ledgers")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(main, "_TURN_GRANTS_FILE", tmp_path / "turn_grants.jsonl")
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", tmp_path / "turn_ledgers")
    return tmp_path


def account(**fields):
    u = {"password_hash": "x", "role": "player", "turn_cap": 30, "turns_used": 0,
         "turn_bonus": 0, "promo_bonus": 0, "reset_date": TODAY,
         "subscription_status": "free", "features": {}}
    u.update(fields)
    return u


def plan_for(users, grants=None, ledgers=None):
    return {r["username"]: r for r in bf.build_plan(users, grants or {}, ledgers or {})}


def test_legacy_bonus_account_gets_an_opening_balance_never_a_purchase():
    plan = plan_for({"gustav": account(turn_bonus=300)})
    assert plan["gustav"]["opening_balance_row"] == 300
    assert plan["gustav"]["pool_data_since"] == TODAY


def test_opening_balance_is_the_remainder_after_logged_grants():
    users = {"chup": account(turn_bonus=464, turns_used_paid_total=100)}
    plan = plan_for(users, grants={"chup": 300})
    assert plan["chup"]["opening_balance_row"] == 464 + 100 - 300


def test_fully_logged_account_gets_no_opening_row():
    """granted == kvar + använt → ledgern är redan komplett (idempotent)."""
    users = {"kalle": account(turn_bonus=200, turns_used_paid_total=100)}
    plan = plan_for(users, grants={"kalle": 300})
    assert "opening_balance_row" not in plan["kalle"]


def test_promo_only_account_gets_no_grant_row():
    """Promo är en egen hink, inte en grant — den får aldrig bli "köpt"."""
    plan = plan_for({"pelle": account(promo_bonus=300)})
    assert "opening_balance_row" not in plan["pelle"]
    assert plan["pelle"]["pool_data_since"] == TODAY


def test_account_without_any_history_is_untouched():
    plan = plan_for({"frida": account()})
    assert plan == {}


def test_ledger_rows_without_bucket_become_known_legacy_turns():
    ledgers = {"frida": {"rows": 5, "unknown": 3}}
    plan = plan_for({"frida": account(turns_used=5)}, ledgers=ledgers)
    assert plan["frida"]["turns_used_unknown_total"] == 3


def test_apply_writes_users_and_grant_rows(tmp_env):
    users = {"gustav": account(turn_bonus=300)}
    tmp_env.joinpath("users.json").write_text(json.dumps(users), encoding="utf-8")
    plan = bf.build_plan(users, {}, {})
    touched, rows = bf.apply_plan(users, plan)

    assert (touched, rows) == (1, 1)
    written = json.loads(tmp_env.joinpath("users.json").read_text())
    assert written["gustav"]["pool_data_since"] == TODAY
    assert written["gustav"]["turn_bonus"] == 300          # saldot rörs aldrig
    grant = json.loads(tmp_env.joinpath("turn_grants.jsonl").read_text().splitlines()[0])
    assert grant["source"] == "opening_balance"
    assert grant["turns"] == 300
    assert grant["user"] == "gustav"
    assert "öppningsbalans" in grant["note"]


def test_second_run_is_a_no_op(tmp_env):
    users = {"gustav": account(turn_bonus=300)}
    bf.apply_plan(users, bf.build_plan(users, bf.grant_totals(), bf.ledger_row_counts()))
    again = bf.build_plan(users, bf.grant_totals(), bf.ledger_row_counts())
    assert all("opening_balance_row" not in r for r in again)
    assert all("pool_data_since" not in r for r in again)


def test_opening_row_reads_as_unknown_purchase_in_the_dashboard():
    """Kärnkravet: efter backfillen är "kvar" exakt, medan "köpt" säger okänt."""
    users = {"gustav": account(turn_bonus=300)}
    bf.apply_plan(users, bf.build_plan(users, {}, {}))
    u = users["gustav"]
    pool = main._turn_pool("gustav", udata=u, grants_index=main._turn_grants_index())
    assert pool["paid"]["left"] == 300
    assert pool["paid"]["granted"] == 300
    assert pool["paid"]["granted_known"] is False          # opening_balance ≠ köp
    assert pool["data_since"] == TODAY
    assert pool["available"] == 330


def test_grant_totals_ignores_broken_lines(tmp_env):
    p = tmp_env / "turn_grants.jsonl"
    p.write_text('{"user":"a","turns":100,"source":"stripe:unlock10"}\n'
                 'inte json\n\n'
                 '{"user":"a","turns":50,"source":"admin"}\n', encoding="utf-8")
    assert bf.grant_totals() == {"a": 150}


def test_ledger_counts_split_bucketed_and_legacy_rows(tmp_env):
    d = tmp_env / "turn_ledgers"
    (d / "frida.jsonl").write_text(
        '{"ts":"2026-09-20T10:00:00+00:00","action":"dm"}\n'
        '{"ts":"2026-09-28T10:00:00+00:00","action":"dm","bucket":"free"}\n'
        '{"ts":"2026-09-28T11:00:00+00:00","action":"dm","bucket":"none"}\n', encoding="utf-8")
    assert bf.ledger_row_counts() == {"frida": {"rows": 3, "unknown": 2}}
