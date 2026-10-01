#!/usr/bin/env python3
"""Backfill: features["supporter"] = True för alla som någonsin betalat.

Bakgrund (2026-10-01): undo-knappen + kampanj-exporten ligger bakom
supporter-grinden (`_is_supporter` i backend/main.py). Flaggan sätts framåt av
varje betalväg (donation / unlock10 / legacy support+patron / lifetime /
admin-grant), men konton som betalade INNAN flaggan fanns måste flaggas — annars
låses de ute ur undo/export trots att de har betalat.

Källor (i denna ordning, aldrig gissning):
  1. backend/data/_billing_ledger.json — betalningsrader (amount_sek > 0 och
     type inte i {stripe:churn, stripe:cancel_scheduled})
  2. backend/data/turn_grants.jsonl — rader med source "stripe:<produkt>"
     ("admin" och "opening_balance" räknas INTE: de är grants/migrering)
  3. users.json — subscription_status == "lifetime", turn_cap == 0 (lifetime),
     eller en betald feature-nyckel (export/wan1080/all_models/unlock10/unlock10)

Körning:
    python3 scripts/backfill_supporter.py            # dry-run (skriver inget)
    python3 scripts/backfill_supporter.py --apply    # skriver + backup först

Backup: backend/data/users.json.bak-<YYYYmmdd-HHMMSS>-supporter (kopieras före
första skrivning). Admin-konton (role=admin) hoppas över — de går alltid förbi
grinden — och redovisas separat. Idempotent: körbar hur många gånger som helst.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "backend" / "data"
USERS_FILE = DATA / "users.json"
BILLING_LEDGER = DATA / "_billing_ledger.json"
TURN_GRANTS = DATA / "turn_grants.jsonl"

PAID_TYPES = {
    "stripe:donation", "stripe:unlock10", "stripe:support300",
    "stripe:patron500", "stripe:tier1", "stripe:tier2", "stripe:lifetime",
}
NON_PAYMENT_TYPES = {"stripe:churn", "stripe:cancel_scheduled"}
PAID_FEATURE_KEYS = ("supporter", "export", "wan1080", "all_models", "unlock10")


def _evidence_billing() -> dict[str, str]:
    """{user: orsak} ur betalningsledgern."""
    out: dict[str, str] = {}
    if not BILLING_LEDGER.exists():
        return out
    try:
        rows = json.loads(BILLING_LEDGER.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! kunde inte läsa {BILLING_LEDGER.name}: {e}")
        return out
    for r in rows if isinstance(rows, list) else []:
        user = (r or {}).get("user")
        typ = str((r or {}).get("type") or "")
        amt = int((r or {}).get("amount_sek") or 0)
        if not user or typ in NON_PAYMENT_TYPES or amt <= 0:
            continue
        if typ in PAID_TYPES or typ.startswith("stripe:"):
            out.setdefault(user, f"billing:{typ} {amt}kr")
    return out


def _evidence_grants() -> dict[str, str]:
    """{user: orsak} ur grant-ledgern (bara stripe-källor)."""
    out: dict[str, str] = {}
    if not TURN_GRANTS.exists():
        return out
    for line in TURN_GRANTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        src = str(rec.get("source") or "")
        user = rec.get("user")
        if not user or not src.startswith("stripe:"):
            continue
        out.setdefault(user, f"grant:{src} {rec.get('turns')}turns")
    return out


def _evidence_account(user: str, udata: dict) -> str | None:
    """Fall 3: kontots EGNA fält (lifetime eller betald feature-nyckel)."""
    if str(udata.get("subscription_status") or "").lower() == "lifetime":
        return "account:lifetime"
    if int(udata.get("turn_cap") or 0) == 0 and udata.get("turn_cap") is not None:
        # turn_cap 0 = oändliga turns (lifetime) i den här modellen.
        if str(udata.get("subscription_status") or "").lower() in ("lifetime", ""):
            return "account:unlimited"
    f = udata.get("features")
    if isinstance(f, dict):
        for k in PAID_FEATURE_KEYS:
            if f.get(k):
                return f"account:features.{k}"
    return None


def main(apply: bool = False) -> int:
    if not USERS_FILE.exists():
        print(f"users.json saknas: {USERS_FILE}")
        return 1
    users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    if not isinstance(users, dict):
        print("users.json har oväntad form — avbryter.")
        return 1

    ev_billing = _evidence_billing()
    ev_grants = _evidence_grants()

    to_flag: dict[str, str] = {}
    already: list[str] = []
    admins: list[str] = []
    for user, udata in users.items():
        if not isinstance(udata, dict):
            continue
        ev = ev_billing.get(user) or ev_grants.get(user) or _evidence_account(user, udata)
        if not ev:
            continue
        if str(udata.get("role") or "") == "admin":
            admins.append(user)
            continue
        f = udata.get("features")
        if isinstance(f, dict) and f.get("supporter"):
            already.append(user)
            continue
        to_flag[user] = ev

    print(f"users.json: {len(users)} konton")
    print(f"  betalningsledger-rader: {len(ev_billing)} användare")
    print(f"  grant-ledger (stripe): {len(ev_grants)} användare")
    print(f"  redan flaggade: {len(already)}")
    print(f"  admin (hoppas över, går förbi grinden): {len(admins)} {admins}")
    print(f"  att flagga: {len(to_flag)}")
    for user, ev in sorted(to_flag.items()):
        cur = (users[user].get("features") or {})
        print(f"    + {user:20s} {ev:28s} (features före: {sorted(cur)})")

    if not to_flag:
        print("Inget att göra — idempotent no-op.")
        return 0
    if not apply:
        print("\nDRY-RUN: inget skrivet. Kör med --apply för att skriva.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = USERS_FILE.with_name(f"users.json.bak-{stamp}-supporter")
    shutil.copy2(USERS_FILE, backup)
    print(f"\nBackup: {backup}")

    for user in to_flag:
        f = users[user].get("features")
        if not isinstance(f, dict):
            f = {}
        f["supporter"] = True
        users[user]["features"] = f

    tmp = USERS_FILE.with_suffix(".json.tmp-supporter")
    # EXAKT samma skrivform som auth.save_users (json.dump, indent=2, default
    # ensure_ascii) så filen inte byter stil bara för att ett skript varit framme.
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    tmp.replace(USERS_FILE)
    print(f"Skrivet: {len(to_flag)} konton flaggade i {USERS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))