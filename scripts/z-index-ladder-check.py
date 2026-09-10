#!/usr/bin/env python3
"""z-index-ladder-check.py — grind för z-index-konstitutionen (snes.css rad 20).

LADDER (enda tillåtna rungar):
  0/1/2/3/4/5/6/7/10  (lokala stackar inne i en komponent)
  40/41/50/60/70/90   (sid-krom)
  100/200/209/210/270 (rader/partiklar)
  0-99 LOKALA stackar (per komponent)
  100/200/209/210/270 (rader/partiklar) < 280 bottom-nav < 290 drawer-backdrop
  < 300 drawer < 310 sheet < 320 oracle/console < 400 d20-overlay < 500 sid-modal
  < 520 mobilmeny < 999 scanlines < 9990 backdrop < 9995 codex-panel (mobil)
  < 10000 sid-overlays < 11000 lightbox < 12000 feedback-backdrop < 12001 feedback-modal
  Inga nya rungar utan att uppdatera snes.css rad 20 OCKSÅ.

Usage: python3 scripts/z-index-ladder-check.py [frontend]
Exit 0 = alla värden på stegen, 1 = avvikelser.
"""
import re, sys, pathlib

# 0-99 = LOKALA stackar inne i en komponent (alltid OK — de konkurrerar bara
# inom sin egen förälder). 100+ = SID-nivå och måste ligga på den dokumenterade stegen.
PAGE_LADDER = {100,200,209,210,270,
               280,290,300,310,320,
               400,500,520,999,1200,
               9990,9995,10000,11000,12000,12001}

def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'frontend')
    bad = {}
    for f in sorted(root.glob('*.html')):
        for i, line in enumerate(f.read_text(encoding='utf-8').split('\n'), 1):
            for m in re.finditer(r'z-index:\s*(-?\d+)', line):
                v = int(m.group(1))
                if v >= 100 and v not in PAGE_LADDER:
                    bad.setdefault(f.name, []).append(f'L{i}: z-index:{v}')
    if bad:
        print('AVVIKELSER från z-index-stegen:')
        for k, v in bad.items():
            print(f'  {k}: ' + ', '.join(v))
        return 1
    print('GREEN — alla z-index på stegen')
    return 0

if __name__ == '__main__':
    sys.exit(main())
