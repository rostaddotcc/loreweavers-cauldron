#!/usr/bin/env python3
"""P3.1 — backfill av turn-potten (2026-09-28, plan: docs/plans/turn-pool-breakdown-2026-09-28.md)

Varför: "hur mycket har spelaren köpt" gick inte att svara på bakåt. `turn_bonus`
är KVARVARANDE, `_billing_ledger.json` har 5 rader och turn-ledgern (67 filer,
1 913 rader, från 2026-08-07) saknade hink. Den här migrationen skriver därför
bara sådant som ÄR SANT idag — aldrig påhittade köp:

  1. `opening_balance`-rad i grant-ledgern per konto, så `granted == kvar + använt`
     stämmer framåt. Beloppet är `turn_bonus + turns_used_paid_total - redan
     bokförda rader` (idempotent: andra körningen skriver inget). Källan
     `opening_balance` räknas av dashboarden som "köp okänt" — den får aldrig
     se ut som ett köp.
  2. `pool_data_since` = 2026-09-28 på konton med gammal historik, så UI:t säger
     "köpt: okänt före 2026-09-28" i stället för att gissa.
  3. `turns_used_unknown_total` = antal ledger-rader UTAN hink (skrivna före
     2026-09-28). Det är känt, mätt och överlever att ledgern beskärs — ersätter
     INTE per-hink-räknarna (en rad utan hink får aldrig kallas "free").

Konto utan pott-historik rörs inte. users.json är det enda som skrivs (grant-
ledgern appendas). Dry-run är förval; `--apply` krävs för att skriva.

Kör i containern (backend/data är bind-mountad):
  docker compose exec loreweavers-cauldron python /app/scripts/backfill_turn_pool.py
  docker compose exec loreweavers-cauldron python /app/scripts/backfill_turn_pool.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TRACKING_SINCE = "2026-09-28"
DATA = Path(os.environ.get("DND_BACKFILL_DATA", "/app/backend/data"))
USERS_FILE = DATA / "users.json"
GRANTS_FILE = DATA / "turn_grants.jsonl"
LEDGERS_DIR = DATA / "turn_ledgers"
DRY = "--apply" not in sys.argv


def load_users(path=None):
    path = Path(path or USERS_FILE)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def grant_totals(path=None):
    """Summan av redan bokförda grant-rader per konto."""
    path = Path(path or GRANTS_FILE)
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        u = row.get("user") or row.get("username")
        if not u:
            continue
        out[u] = out.get(u, 0) + int(row.get("turns") or 0)
    return out


def ledger_row_counts(ledgers_dir=None):
    """Antal ledger-rader per konto, och hur många av dem som saknar hink.

    Hink-lösa rader är skrivna före 2026-09-28 — de är "unknown", aldrig "free".
    """
    ledgers_dir = Path(ledgers_dir or LEDGERS_DIR)
    out = {}
    if not ledgers_dir.exists():
        return out
    for p in sorted(ledgers_dir.glob("*.jsonl")):
        total = 0
        unknown = 0
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            total += 1
            if not row.get("bucket") or row.get("bucket") == "none":
                unknown += 1
        if total:
            out[p.stem] = {"rows": total, "unknown": unknown}
    return out


def build_plan(users, grants, ledgers):
    """Vad som skulle ändras — ren funktion, ingen I/O (testbar)."""
    plan = []
    for name, u in sorted(users.items()):
        if not isinstance(u, dict):
            continue
        cap = int(u.get("turn_cap", 0) or 0)
        used_period = int(u.get("turns_used", 0) or 0)
        promo = int(u.get("promo_bonus", 0) or 0)
        bonus = int(u.get("turn_bonus", 0) or 0)
        used_paid = int(u.get("turns_used_paid_total", 0) or 0)
        used_free = int(u.get("turns_used_free_total", 0) or 0)
        used_promo = int(u.get("turns_used_promo_total", 0) or 0)
        rows = ledgers.get(name) or {}
        unknown_rows = int(rows.get("unknown") or 0)
        # Har kontot någon pott-historik alls? Ren gratispott utan spelade turns
        # behöver ingen ärlighetsgräns.
        has_history = bool(bonus or promo or used_period or used_paid or used_free or used_promo or rows.get("rows"))
        opening = bonus + used_paid - int(grants.get(name) or 0)
        changes = {}
        if has_history and not u.get("pool_data_since"):
            changes["pool_data_since"] = TRACKING_SINCE
        if unknown_rows and int(u.get("turns_used_unknown_total", 0) or 0) != unknown_rows:
            changes["turns_used_unknown_total"] = unknown_rows
        if opening > 0:
            changes["opening_balance_row"] = opening
        if changes:
            plan.append({
                "username": name, "cap": cap, "turn_bonus": bonus, "promo_bonus": promo,
                "used_period": used_period, "used_paid": used_paid,
                "ledger_rows": int(rows.get("rows") or 0), "ledger_unknown": unknown_rows,
                "granted_logged": int(grants.get(name) or 0), **changes,
            })
    return plan


def apply_plan(users, plan, users_path=None, grants_path=None):
    """Skriv planen. Returnerar (antal users-ändringar, antal grant-rader)."""
    users_path = Path(users_path or USERS_FILE)
    grants_path = Path(grants_path or GRANTS_FILE)
    rows = []
    touched = 0
    for item in plan:
        u = users.get(item["username"])
        if not isinstance(u, dict):
            continue
        if "pool_data_since" in item:
            u["pool_data_since"] = item["pool_data_since"]
        if "turns_used_unknown_total" in item:
            u["turns_used_unknown_total"] = item["turns_used_unknown_total"]
        touched += 1
        opening = item.get("opening_balance_row")
        if opening:
            rows.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                # "user" — SAMMA nyckel som _append_turn_grant skriver. Två namn
                # på samma fält är precis hur "köpt" blev felräknat förut.
                "user": item["username"],
                "turns": int(opening),
                "source": "opening_balance",
                "left_after": int(item["turn_bonus"]),
                "pool_after": int(item["turn_bonus"]) + int(item["promo_bonus"]),
                "note": "öppningsbalans 2026-09-28: köp/grants före denna dag finns inte loggade",
            })
    if rows:
        with open(grants_path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp = users_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(users_path)
    return touched, len(rows)


def main():
    users = load_users()
    if not users:
        print(f"inget att göra: {USERS_FILE} saknas eller är tom")
        return 1
    plan = build_plan(users, grant_totals(), ledger_row_counts())
    header = "DRY-RUN" if DRY else "APPLIED"
    print(f"{header} — {len(plan)} konton berörs av turn-pott-backfillen\n")
    print(f"  {'konto':14} {'bonus':>6} {'promo':>6} {'använt':>7} {'ledger':>7} {'=okänd':>7} {'bokfört':>8} {'öppning':>8}")
    for r in plan:
        print(f"  {r['username']:14} {r['turn_bonus']:>6} {r['promo_bonus']:>6} {r['used_period']:>7} "
              f"{r['ledger_rows']:>7} {r['ledger_unknown']:>7} {r['granted_logged']:>8} {r.get('opening_balance_row', 0):>8}")
    opens = [r for r in plan if r.get("opening_balance_row")]
    print(f"\n  {len(opens)} konton får en opening_balance-rad (köp okänt före {TRACKING_SINCE})")
    print(f"  {len([r for r in plan if 'pool_data_since' in r])} konton får pool_data_since")
    print(f"  {len([r for r in plan if 'turns_used_unknown_total' in r])} konton får kända legacy-turns")
    if DRY:
        print("\n  Inget skrivet. Kör med --apply för att genomföra (backup tas först).")
        return 0
    backup = USERS_FILE.with_suffix(f".json.bak-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-turnpool")
    shutil.copy2(USERS_FILE, backup)
    touched, grant_rows = apply_plan(users, plan)
    print(f"\n  backup → {backup}")
    print(f"  skrev {touched} konton i users.json och {grant_rows} rader i {GRANTS_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
