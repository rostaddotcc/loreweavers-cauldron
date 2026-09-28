#!/usr/bin/env python3
"""Ta bort legacy signup-promo (promo_bonus) — 2026-09-28.

Beslut av rostad: endast betalande spelare får behålla "patron"-gradens legacy
turns; alla andra = 30 turns/dag (free tier).

Regler:
  - Betalande = rad med amount_sek > 0 i backend/data/_billing_ledger.json
    (nomis, andreasmaurel, chup). Deras promo_bonus rörs INTE
    (samtliga har redan 0 — deras köpta turns ligger i turn_bonus och rörs ej).
  - Alla övriga konton: promo_bonus -> 0.
  - turn_cap sätts till 30 endast för icke-betalande med avvikande cap
    (boblin 300). Cap 0 = köpt lifetime, rörs ej.
  - turns_used_promo_total är historik och står still.
  - Admin-konton (simon, mainchat) är inte betalande och följer samma regel.

Backup skrivs automatiskt. --apply för att skriva, annars dry-run.
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "backend" / "data"
APPLY = "--apply" in sys.argv


def main() -> int:
    users = json.loads((DATA / "users.json").read_text())

    payers = set()
    for row in json.loads((DATA / "_billing_ledger.json").read_text()):
        if float(row.get("amount_sek") or 0) > 0:
            payers.add(row["user"])

    cleared, protected, capped = [], [], []
    for name, u in users.items():
        if not isinstance(u, dict):
            continue
        promo = int(u.get("promo_bonus") or 0)
        if promo > 0:
            if name in payers:
                protected.append((name, promo))
            else:
                cleared.append((name, promo))
                u["promo_bonus"] = 0
        cap = int(u.get("turn_cap") or 0)
        if cap not in (0, 30) and name not in payers:
            capped.append((name, cap))
            u["turn_cap"] = 30

    print(f"payers: {sorted(payers)}")
    print(f"promo rensas på {len(cleared)} konton "
          f"({sum(p for _, p in cleared)} turns totalt)")
    print(f"promo skyddas (betalande): {protected}")
    print(f"cap normaliseras till 30: {capped}")

    if not APPLY:
        print("DRY-RUN — ingen fil skriven. Kör med --apply.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = DATA / f"users.json.bak-{stamp}-legacy-promo"
    shutil.copy2(DATA / "users.json", bak)
    tmp = DATA / "users.json.tmp"
    tmp.write_text(json.dumps(users, indent=2))
    tmp.replace(DATA / "users.json")
    print(f"backup: {bak}")
    print("skrev users.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
