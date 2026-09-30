#!/usr/bin/env python3
"""Ta bort intro-startbonus (300/100 turns i turn_bonus) — 2026-09-28, del 2.

Endast betalande (chup, andreasmaurel, nomis — rad med amount_sek>0 i
_billing_ledger.json) behåller sin pott. Övrigas intro-grants var ej betalda
och anses utgångna efter intro-månaden: turn_bonus -> 0.

Grant-ledgern: `opening_balance`-raden för varje nollat konto skrivs om till
`expired_intro` med turns=0 / left_after=0 (raden behålls som revisionsspår;
invarianten granted == left + paid_total håller eftersom den nollade
startbonusen aldrig bokfördes som paid — kontona har turns_used_paid_total=0).
Riktiga köp-rader (stripe:*, admin) rör aldrig: inga sådana finns utanför
betalanda.

Historiska räknare (turns_used_*) står still. Backup tas automatiskt.
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
    payers = {r["user"] for r in json.loads((DATA / "_billing_ledger.json").read_text())
              if float(r.get("amount_sek") or 0) > 0}

    zeroed = []
    for name, u in users.items():
        if not isinstance(u, dict):
            continue
        bonus = int(u.get("turn_bonus") or 0)
        if bonus > 0 and name not in payers:
            zeroed.append((name, bonus))
            u["turn_bonus"] = 0

    print(f"betalare (sparas): {sorted(payers)}")
    print(f"turn_bonus nollas på {len(zeroed)} konton: {zeroed}")

    grants = [json.loads(l) for l in (DATA / "turn_grants.jsonl").read_text().splitlines() if l.strip()]
    names_zeroed = {n for n, _ in zeroed}
    expired_users = set()
    for g in grants:
        if g.get("user") in names_zeroed and g.get("source") == "opening_balance":
            g["turns"] = 0
            g["left_after"] = 0
            g["note"] = "intro-startbonus utgången 2026-09-28 (icke-betalande)"
            expired_users.add(g["user"])
    print(f"opening_balance-rader markerade: {sorted(expired_users)}")

    if not APPLY:
        print("DRY-RUN — ingen fil skriven.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(DATA / "users.json", DATA / f"users.json.bak-{stamp}-intro-bonus")
    shutil.copy2(DATA / "turn_grants.jsonl", DATA / f"turn_grants.jsonl.bak-{stamp}-intro-bonus")
    tmp = DATA / "users.json.tmp"
    tmp.write_text(json.dumps(users, indent=2))
    tmp.replace(DATA / "users.json")
    (DATA / "turn_grants.jsonl").write_text(
        "\n".join(json.dumps(g) for g in grants) + "\n")
    print("skrev users.json + turn_grants.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
