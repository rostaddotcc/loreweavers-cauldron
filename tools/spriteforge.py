#!/usr/bin/env python3
"""
spriteforge.py — Mörkrets Rike icon forge
==========================================
Ritar 16×16 pixel-sigils (originaldesigner, INGA emoji-kopior) via primitiver
och genererar:
  1. frontend/sprites.js  (v2 — semantiska namn + emoji-mappning + renderer)
  2. tools/sprite-preview.html  (förhandsvisningssida för godkännande)

Stilregler (terminal-gothic):
  - 1px outline i G/g (guld), w (ben) eller s (stål) — aldrig diffusa kanter
  - mörk fyllning (k) som bas, accentfärg per betydelse
  - ljus ovanifrån-vänster: highlight-rad upptill, skugga nertill
  - 16×16 canvas, ikonen centrerad med ~1px luft
"""

import json, os

W, H = 16, 16
DOT = '.'

# ── Palett (matchar sprites.js v1) ──
PAL = {
    '.': None,
    'k': '#0a0a12',   # bläck
    'w': '#e0e0ec',   # ben
    'd': '#6a6a80',   # dämpad grå
    's': '#a8b2c0',   # stål
    'i': '#4a4a6a',   # järn
    'g': '#c9a227',   # guld
    'G': '#e8c65a',   # ljust guld
    'r': '#d43a4d',   # blod
    'R': '#8b1a2a',   # mörkt blod
    'p': '#7b4fd4',   # arkan
    'P': '#a88ae8',   # ljust arkan
    'n': '#33cc33',   # natur
    'N': '#5a9a4e',   # dämpad natur
    'o': '#d4691e',   # eld
    't': '#4e8a93',   # teal
    'b': '#8a6d3f',   # läder
    'B': '#5a4433',   # mörkt läder
    'f': '#e0b080',   # hud
    'c': '#33cccc',   # cyan
}

class Canvas:
    def __init__(self):
        self.g = [[DOT]*W for _ in range(H)]
    # ── primitiver ──
    def px(self, c, x, y):
        if 0 <= x < W and 0 <= y < H:
            self.g[y][x] = c
    def clear(self, x, y, w=1, h=1):
        for yy in range(y, y+h):
            for xx in range(x, x+w):
                if 0 <= xx < W and 0 <= yy < H:
                    self.g[yy][xx] = DOT
    def hline(self, c, y, x1, x2):
        if x2 < x1: x1, x2 = x2, x1
        for x in range(x1, x2+1): self.px(c, x, y)
    def vline(self, c, x, y1, y2):
        if y2 < y1: y1, y2 = y2, y1
        for y in range(y1, y2+1): self.px(c, x, y)
    def line(self, c, x1, y1, x2, y2):
        dx, dy = abs(x2-x1), abs(y2-y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        while True:
            self.px(c, x1, y1)
            if x1 == x2 and y1 == y2: break
            e2 = 2*err
            if e2 > -dy: err -= dy; x1 += sx
            if e2 < dx:  err += dx; y1 += sy
    def rect(self, c, x, y, w, h):
        self.hline(c, y, x, x+w-1); self.hline(c, y+h-1, x, x+w-1)
        self.vline(c, x, y, y+h-1); self.vline(c, x+w-1, y, y+h-1)
    def fill(self, c, x, y, w, h):
        for yy in range(y, y+h): self.hline(c, yy, x, x+w-1)
    def diamond(self, c, cx, cy, r):
        for dy in range(-r, r+1):
            half = r - abs(dy)
            for dx in range(-half, half+1): self.px(c, cx+dx, cy+dy)
    def disc(self, c, cx, cy, r):
        for dy in range(-r, r+1):
            for dx in range(-r, r+1):
                if dx*dx + dy*dy <= r*r + r*0.4: self.px(c, cx+dx, cy+dy)
    def ring(self, c, cx, cy, r):
        self.disc(c, cx, cy, r)
        self.disc(DOT, cx, cy, r-1) if r > 1 else None
    def tri(self, c, x1, y1, x2, y2, x3, y3):
        pts = [(x1, y1), (x2, y2), (x3, y3)]
        pts.sort(key=lambda p: p[1])
        (x1, y1), (x2, y2), (x3, y3) = pts
        def edge(xa, ya, xb, yb, y):
            if yb == ya: return None
            if not (min(ya, yb) <= y <= max(ya, yb)): return None
            return xa + (y - ya) * (xb - xa) / (yb - ya)
        for y in range(y1, y3+1):
            xs = sorted({e for e in [edge(x1,y1,x2,y2,y), edge(x2,y2,x3,y3,y), edge(x1,y1,x3,y3,y)] if e is not None})
            if len(xs) >= 2:
                a, b = int(xs[0]), int(xs[-1])
                for x in range(a, b+1): self.px(c, x, y)
    # ── utdata ──
    def rows(self):
        return [''.join(row) for row in self.g]
    def svg(self, px=1):
        rects = []
        for y, row in enumerate(self.g):
            for x, ch in enumerate(row):
                col = PAL.get(ch)
                if not col: continue
                rects.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{col}"/>')
        return ('<svg viewBox="0 0 16 16" shape-rendering="crispEdges" width="%d" height="%d">%s</svg>'
                % (px*16, px*16, ''.join(rects)))

# ══════════════════════════════════════════════════════════════
#  IKONER — originaldesigner (semantiskt namn → ritfunktion)
# ══════════════════════════════════════════════════════════════
# Konvention: outline G/w/s 1px, fyllning k/d, accentfärg per betydelse,
# highlight-pixlar G/P/w upptill-vänster, skugga d/i nertill-höger.

def i_menu(c):
    """☰ hamburger — tre guldbarer med highlight"""
    for y, yb in ((3,5),(7,9),(11,13)):
        c.hline('G', y, 3, 12)
        for x in range(3, 13): c.px('g', x, y+1) if False else None
        c.hline('g', y+1, 4, 11) if yb-y == 2 else None

def i_codex(c):
    """📖 stängd codex — blodrött läder, guldslås, benpärm"""
    c.rect('w', 2, 3, 12, 10)          # ytterpärm
    c.rect('R', 3, 4, 10, 8)           # läder
    c.hline('r', 4, 4, 11); c.hline('r', 10, 4, 11)
    c.vline('r', 4, 5, 9); c.vline('r', 11, 5, 9)
    c.vline('G', 8, 3, 12)             # rygg/guldstång
    c.vline('g', 9, 3, 12)
    c.diamond('G', 8, 6, 1); c.px('g', 8, 7)
    c.px('w', 2, 4); c.px('w', 2, 11)

def i_gear(c):
    """⚙ inställningar — runisk kugge guld/järn (ring r4 handplacerad)"""
    ring4 = [(4,8),(12,8),(8,4),(8,12),(5,5),(6,5),(11,5),(10,5),
             (5,11),(6,11),(11,11),(10,11),(4,7),(4,9),(12,7),(12,9),
             (7,4),(9,4),(7,12),(9,12)]
    for x, y in ring4: c.px('g', x, y)
    # tänder (utanför ringen)
    for (dx, dy) in [(0,-4),(0,4),(-4,0),(4,0),(-3,-3),(3,-3),(-3,3),(3,3)]:
        c.px('g', 8+dx, 8+dy)
    # nav
    c.disc('i', 8, 8, 2)
    c.diamond('g', 8, 8, 1)
    c.px('G', 6, 5); c.px('G', 7, 5)

def i_quill(c):
    """✍ fjäderpenna — benfjäder, guldspets, bläckdroppe"""
    c.line('w', 5, 3, 11, 9)           # skaft
    c.px('w', 4, 4); c.px('w', 3, 5); c.px('w', 3, 6); c.px('w', 4, 7); c.px('w', 5, 8)
    c.px('d', 4, 6); c.px('d', 5, 7)
    c.px('w', 6, 4); c.px('w', 7, 5); c.px('w', 8, 6)
    c.px('g', 11, 9); c.px('g', 11, 10); c.px('g', 12, 10)  # spets
    c.px('r', 10, 13); c.px('r', 11, 13); c.px('r', 12, 12); c.px('r', 12, 14)  # bläck

def i_dice(c):
    """🎲 tärning — ben-d20 med guldpipor"""
    c.diamond('w', 8, 8, 6)
    c.diamond('d', 8, 8, 5)
    c.px('k', 8, 8)
    c.px('G', 5, 5); c.px('g', 6, 6)
    c.diamond('G', 8, 8, 1)
    c.diamond('g', 5, 11, 1); c.diamond('g', 11, 5, 1); c.diamond('g', 11, 11, 1)

def i_mask(c):
    """🎭 avatar — teatermask guld/bon"""
    c.rect('w', 3, 4, 10, 8)
    c.diamond('G', 8, 7, 4)            # ansikte guld
    c.px('k', 5, 6); c.px('k', 11, 6)  # ögon
    c.diamond('k', 8, 9, 1)            # mun
    c.px('w', 3, 5); c.px('w', 3, 10)

def i_battle(c):
    """⚔ strid — korsade svärd stål + guld"""
    c.line('s', 3, 3, 12, 10); c.line('s', 3, 10, 12, 3)
    c.line('w', 4, 3, 13, 10); c.line('w', 4, 10, 13, 3)  # eggar
    c.px('g', 3, 3); c.px('g', 3, 10); c.px('g', 12, 3); c.px('g', 12, 10)
    c.px('g', 7, 7); c.px('G', 7, 6); c.px('G', 6, 7); c.px('g', 6, 6)  # korsfäste
    c.px('r', 8, 4); c.px('r', 8, 5); c.px('r', 5, 8); c.px('r', 5, 9)

def i_quest(c):
    """⚑ uppdrag — blodröd baner på stålstång"""
    c.vline('s', 3, 2, 13)
    c.px('G', 3, 2); c.px('g', 3, 3)
    c.tri('r', 4, 4, 13, 6, 4, 9)
    c.tri('R', 4, 10, 11, 12, 4, 13)
    c.px('w', 8, 5); c.px('w', 6, 6); c.px('w', 10, 7)

def i_map(c):
    """🗺 karta — pergament med berg + guldväg"""
    c.rect('w', 2, 3, 12, 10)
    c.hline('g', 3, 3, 12); c.hline('g', 12, 3, 12)
    c.px('d', 2, 4); c.px('d', 2, 12)
    c.tri('d', 5, 10, 7, 6, 9, 10)     # berg
    c.tri('w', 5, 10, 6, 8, 7, 10)
    c.px('n', 10, 9); c.px('n', 11, 10)
    c.line('G', 4, 11, 12, 6)          # guldväg
    c.px('r', 12, 6); c.px('r', 11, 7)

def i_pin(c):
    """📌 kartnål — guldhuvud, stålspets"""
    c.disc('G', 8, 5, 2); c.disc('g', 8, 5, 1)
    c.vline('s', 8, 7, 11)
    c.px('s', 7, 11); c.px('s', 8, 12); c.px('s', 9, 11)
    c.px('r', 8, 5)

def i_npc(c):
    """🧝 NPC — huva-siluett ben/mörk"""
    c.tri('w', 8, 2, 4, 6, 12, 6)      # huva
    c.tri('k', 8, 3, 5, 6, 11, 6)
    c.rect('w', 5, 6, 6, 7)            # kropp
    c.fill('k', 6, 7, 4, 5)
    c.px('G', 8, 4); c.px('G', 7, 5)   # ögonläs
    c.vline('d', 5, 8, 11); c.vline('d', 10, 8, 11)

def i_bag(c):
    """🎒 väska — läder med guldbuckla"""
    c.rect('b', 3, 5, 10, 8)
    c.rect('B', 4, 6, 8, 6)
    c.rect('w', 4, 4, 8, 2)            # lock
    c.px('g', 7, 4); c.px('g', 8, 4); c.px('G', 7, 5); c.px('G', 8, 5)
    c.diamond('g', 8, 9, 1)            # buckla
    c.px('G', 4, 5)

def i_brain(c):
    """🧠 modeller — arkan hjärna"""
    c.disc('p', 6, 8, 4); c.disc('p', 10, 8, 4)
    c.disc('P', 6, 7, 2); c.disc('P', 10, 7, 2)
    c.px('k', 6, 8); c.px('k', 10, 8)
    c.line('P', 8, 5, 8, 11)
    c.px('P', 7, 10); c.px('P', 9, 10); c.px('P', 6, 12); c.px('P', 10, 12)
    c.px('P', 5, 9); c.px('P', 11, 9)

def i_crown(c):
    """👑 admin — guldkrona med blodrubiner"""
    c.hline('G', 4, 4, 12)
    c.tri('G', 4, 4, 6, 2, 8, 4)
    c.tri('G', 8, 4, 10, 2, 12, 4)
    c.tri('g', 6, 2, 6, 4, 7, 4) if False else None
    c.rect('g', 4, 5, 9, 2)
    c.hline('g', 7, 4, 12)
    c.px('r', 6, 3); c.px('r', 10, 3); c.px('P', 8, 5)
    c.px('w', 4, 4); c.px('w', 12, 4)

def i_horn(c):
    """🔊 ljud — krigshorn ben med ljudvågor"""
    c.line('w', 4, 12, 10, 6)          # hornkropp
    c.line('w', 5, 13, 11, 7)
    c.px('w', 4, 12); c.px('w', 5, 13) # munstycke
    c.diamond('w', 12, 5, 2)           # klocka
    c.px('k', 12, 5)
    c.px('G', 6, 11); c.px('G', 7, 10)
    c.px('t', 14, 5); c.px('t', 13, 8); c.px('t', 14, 11)
    c.px('c', 14, 6); c.px('c', 14, 9)

def i_refresh(c):
    """🔄 uppdatera — cirkulära pilar stål"""
    c.line('s', 5, 4, 10, 4)           # topp
    c.line('s', 11, 5, 11, 9)          # höger
    c.line('s', 10, 12, 5, 12)         # botten
    c.line('s', 4, 11, 4, 7)           # vänster
    c.px('G', 11, 4); c.px('G', 12, 3); c.px('G', 12, 5)   # högerpil
    c.px('G', 5, 12); c.px('G', 4, 11); c.px('G', 4, 13)   # vänsterpil
    c.px('d', 8, 8)

def i_engine(c):
    """🛠 maskinrum — korsade verktyg stål/guld"""
    c.line('s', 5, 4, 10, 9)
    c.line('s', 11, 4, 6, 9)
    c.hline('s', 3, 4, 6); c.px('G', 4, 3); c.px('G', 5, 3)
    c.hline('s', 3, 10, 12); c.px('G', 11, 3); c.px('G', 12, 3)
    c.line('i', 10, 9, 11, 12); c.line('i', 6, 9, 5, 12)
    c.px('b', 8, 7); c.px('B', 8, 8); c.px('G', 7, 7); c.px('G', 8, 6)

def i_door(c):
    """🚪 lämna — port med guldbeslag"""
    c.line('w', 4, 2, 2, 6); c.line('w', 12, 2, 14, 6)   # båge
    c.vline('w', 2, 6, 13); c.vline('w', 14, 6, 13)
    c.hline('w', 2, 4, 12); c.hline('w', 13, 2, 14)
    c.fill('k', 4, 3, 8, 10)           # öppning
    c.px('o', 4, 5); c.px('o', 5, 4); c.px('o', 5, 5)    # fackla
    c.vline('g', 8, 5, 11); c.diamond('g', 8, 4, 1)      # beslag
    c.px('G', 8, 5)

def i_cli(c):
    """🖥 terminal — '>_' med markör"""
    c.rect('s', 2, 4, 12, 8)
    c.fill('k', 3, 5, 10, 6)
    c.px('n', 4, 6); c.px('n', 5, 6); c.px('n', 6, 6)    # prompt
    c.px('G', 8, 6); c.px('G', 9, 6); c.px('G', 10, 6)   # skrivet
    c.px('G', 11, 6)                                     # markör
    c.px('w', 3, 8); c.px('w', 4, 8); c.px('w', 5, 8)    # blinkrad
    c.px('i', 2, 10); c.px('i', 3, 10); c.px('i', 4, 10); c.px('i', 5, 10)

def i_bolt(c):
    """⚡ energi — guldblixt"""
    c.tri('G', 8, 2, 4, 9, 8, 9)
    c.tri('g', 8, 2, 7, 9, 8, 9)
    c.tri('G', 8, 7, 12, 13, 8, 13)
    c.tri('g', 8, 7, 9, 13, 8, 13)
    c.px('w', 6, 5); c.px('w', 10, 10)

def i_stats(c):
    """📊 användning — tre stigande staplar"""
    c.rect('s', 2, 3, 12, 10)
    c.fill('k', 3, 4, 10, 8)
    c.vline('i', 3, 4, 11); c.vline('i', 6, 4, 11); c.vline('i', 9, 4, 11)
    c.hline('i', 8, 3, 11); c.hline('i', 5, 3, 11)
    c.fill('g', 4, 10, 2, 2); c.fill('G', 4, 8, 2, 2)
    c.fill('g', 7, 8, 2, 4); c.fill('G', 7, 6, 2, 2)
    c.fill('g', 10, 6, 2, 6); c.fill('G', 10, 4, 2, 2)

def i_chat(c):
    """💬 feedback — pratbubbla ben + guldstjärt"""
    c.rect('w', 3, 4, 10, 8)
    c.fill('k', 4, 5, 8, 6)
    c.px('w', 3, 10); c.px('w', 4, 11); c.px('w', 5, 12)
    c.px('G', 6, 6); c.px('G', 7, 6); c.px('G', 8, 6); c.px('G', 9, 6)
    c.px('d', 6, 8); c.px('d', 7, 8); c.px('d', 8, 8)
    c.px('w', 3, 5); c.px('w', 3, 11)

def i_chest(c):
    """📦 export — träkista med guldband"""
    c.rect('b', 3, 7, 10, 6)
    c.rect('B', 4, 8, 8, 4)
    c.rect('w', 3, 4, 10, 3)           # lock
    c.rect('b', 4, 5, 8, 2)
    c.vline('g', 7, 4, 9); c.vline('g', 8, 4, 9)
    c.diamond('G', 8, 8, 1)            # lås
    c.px('G', 4, 5); c.px('G', 11, 5)

def i_palette(c):
    """🎨 tema — palett med färgdroppar"""
    c.disc('b', 7, 8, 5)
    c.px('B', 3, 6); c.px('B', 3, 10); c.px('B', 5, 12)
    c.disc('k', 7, 9, 3)
    c.px('r', 5, 7); c.px('n', 8, 7); c.px('t', 6, 10); c.px('G', 9, 10)
    c.px('w', 3, 8); c.px('w', 12, 8); c.px('w', 7, 4)

def i_lock(c):
    """🔒 lås — järnkropp med guldbåge"""
    c.ring('G', 7, 5, 3)               # båge
    c.rect('i', 4, 7, 8, 6)
    c.rect('s', 5, 8, 6, 4)
    c.px('k', 7, 8); c.px('k', 8, 8); c.px('k', 7, 9); c.px('k', 8, 10)
    c.px('G', 5, 8); c.px('G', 6, 8)

def i_skull(c):
    """💀 död — benkranium med blodögonsken"""
    c.disc('w', 8, 6, 4)
    c.disc('d', 8, 7, 3)
    c.px('k', 6, 6); c.px('k', 10, 6)
    c.px('r', 6, 5); c.px('r', 10, 5)
    c.tri('k', 8, 8, 7, 10, 9, 10)
    c.hline('w', 11, 5, 11)
    c.px('w', 5, 12); c.px('w', 7, 12); c.px('w', 9, 12); c.px('w', 11, 12)
    c.px('w', 4, 6); c.px('w', 4, 7)

def i_warn(c):
    """⚠ varning — guldtriangel med bläck-!"""
    c.tri('G', 8, 2, 2, 14, 14, 14)
    c.tri('g', 8, 4, 3, 13, 13, 13)
    c.tri('k', 8, 5, 4, 12, 12, 12)
    c.vline('w', 8, 6, 9); c.px('w', 8, 11)

def i_feather(c):
    """🪶 fjäder — skrivarfjäder ben"""
    c.line('w', 4, 2, 11, 13)          # skaft
    c.line('d', 5, 3, 10, 12)          # innerkant
    c.px('w', 3, 3); c.px('w', 3, 4); c.px('w', 4, 4); c.px('w', 3, 5); c.px('w', 4, 6); c.px('w', 5, 7)
    c.px('w', 5, 2); c.px('w', 6, 3); c.px('w', 7, 4); c.px('w', 8, 5)
    c.px('d', 4, 5); c.px('d', 5, 6); c.px('d', 6, 7); c.px('d', 7, 8)
    c.px('g', 11, 13); c.px('g', 11, 14)  # spets
    c.px('r', 9, 10); c.px('r', 10, 11)

def i_owl(c):
    """🦉 Lorekeeper — uggla arkan"""
    c.tri('p', 8, 2, 4, 6, 12, 6)      # örontofsar+huvud
    c.tri('P', 8, 3, 5, 6, 11, 6)
    c.rect('p', 5, 6, 6, 7)            # kropp
    c.fill('P', 6, 7, 4, 5)
    c.px('G', 6, 4); c.px('G', 10, 4)  # ögon
    c.px('k', 7, 5); c.px('k', 9, 5)
    c.tri('o', 8, 6, 7, 8, 9, 8)       # näbb
    c.vline('p', 6, 9, 11); c.vline('p', 10, 9, 11)
    c.px('w', 8, 12); c.px('w', 7, 12); c.px('w', 9, 12)

def i_wizard(c):
    """🧙 karaktär — trollkarl arkan"""
    c.tri('p', 8, 2, 4, 7, 12, 7)      # hatt
    c.tri('P', 8, 3, 5, 7, 11, 7)
    c.px('G', 8, 3); c.px('G', 7, 4)   # stjärna
    c.px('f', 6, 8); c.px('f', 7, 8); c.px('f', 8, 8); c.px('f', 9, 8); c.px('f', 10, 8)
    c.px('k', 6, 9); c.px('k', 9, 9)   # ögon
    c.disc('P', 8, 12, 3)              # mantel
    c.px('p', 8, 11); c.px('p', 7, 11); c.px('p', 9, 11)
    c.px('w', 5, 10); c.px('w', 11, 10)

def i_dm(c):
    """🧙♂️ DM — guldtrollkarl med stav + arkan-klot"""
    c.tri('G', 8, 1, 4, 6, 12, 6)      # guldhatt
    c.tri('g', 8, 2, 5, 6, 11, 6)
    c.px('w', 8, 3)                    # stjärna
    c.px('f', 6, 7); c.px('f', 7, 7); c.px('f', 8, 7); c.px('f', 9, 7); c.px('f', 10, 7)
    c.px('k', 6, 8); c.px('k', 9, 8)
    c.rect('G', 5, 9, 6, 3)            # guldmantel
    c.px('g', 4, 9); c.px('g', 11, 9)
    c.vline('s', 13, 5, 11)            # stav
    c.ring('P', 13, 4, 2); c.px('P', 13, 3); c.px('w', 13, 4)
    c.px('k', 13, 4)

def i_heart(c):
    """❤ liv — blodhjärta med guldkant"""
    c.tri('R', 8, 4, 5, 8, 11, 8) if False else None
    c.disc('R', 5, 6, 3); c.disc('R', 11, 6, 3)
    c.tri('R', 4, 8, 12, 8, 8, 13)
    c.disc('r', 5, 6, 2); c.disc('r', 11, 6, 2)
    c.tri('r', 5, 8, 11, 8, 8, 12)
    c.px('G', 4, 5); c.px('G', 5, 5)
    c.px('r', 4, 9); c.px('r', 12, 9)

def i_coin(c):
    """🪙 mynt — guldmynt med sigill"""
    c.ring('G', 8, 8, 5)
    c.ring('g', 8, 8, 4)
    c.disc('G', 8, 8, 3)
    c.disc('g', 8, 8, 2)
    c.diamond('k', 8, 8, 1)
    c.px('w', 8, 8)
    c.px('G', 6, 6); c.px('G', 7, 6)

def i_torch(c):
    """🕯 fackla/levande ljus — eld + hållare"""
    c.tri('o', 8, 3, 5, 8, 11, 8)
    c.tri('G', 8, 4, 6, 8, 10, 8)
    c.px('w', 8, 4)
    c.vline('b', 8, 8, 10)
    c.px('b', 7, 8); c.px('b', 9, 8)
    c.hline('b', 10, 7, 9)
    c.hline('s', 11, 6, 10)
    c.px('o', 7, 5); c.px('o', 9, 5)

def i_fire(c):
    """🔥 eld — flamsigill"""
    c.tri('o', 8, 2, 4, 10, 8, 10)
    c.tri('G', 7, 4, 5, 9, 8, 9)
    c.tri('r', 9, 7, 11, 12, 8, 12)
    c.px('G', 7, 3); c.px('G', 8, 3); c.px('G', 6, 5)
    c.px('w', 8, 2)
    c.px('o', 5, 11); c.px('o', 6, 12); c.px('r', 9, 13)

def i_leaf(c):
    """🌿 ört — kvist med blad"""
    c.line('n', 8, 2, 8, 13)
    c.px('n', 8, 1)
    c.tri('n', 5, 5, 8, 3, 8, 7)          # vänster toppblad
    c.tri('N', 8, 6, 11, 5, 11, 9)        # höger mittblad
    c.tri('n', 4, 10, 8, 9, 8, 12)        # vänster bottenblad
    c.tri('N', 8, 11, 12, 12, 8, 14)      # höger bottenblad
    c.px('G', 6, 4); c.px('G', 10, 6); c.px('G', 5, 10); c.px('G', 11, 12)

def i_tree(c):
    """🌲 tall — gran"""
    c.tri('n', 8, 2, 3, 8, 13, 8)
    c.tri('N', 8, 5, 4, 10, 12, 10)
    c.tri('n', 8, 8, 5, 12, 11, 12)
    c.vline('b', 8, 12, 14)
    c.px('B', 7, 12); c.px('B', 9, 12)
    c.px('G', 6, 4); c.px('G', 10, 6)

def i_mountain(c):
    """⛰ berg — snötäckta toppar"""
    c.tri('d', 3, 13, 8, 3, 13, 13)
    c.tri('w', 5, 9, 8, 3, 11, 9)
    c.tri('i', 9, 13, 12, 7, 15, 13)
    c.tri('w', 11, 10, 12, 7, 13, 10)
    c.px('G', 8, 3)
    c.hline('B', 13, 3, 14)
    c.px('d', 8, 4)

def i_water(c):
    """🌊 vatten — teal-vågor"""
    c.hline('t', 5, 3, 13)
    c.hline('c', 6, 5, 13)
    c.hline('t', 9, 2, 13)
    c.hline('c', 10, 4, 12)
    c.hline('t', 13, 2, 11)
    c.px('c', 3, 5); c.px('c', 2, 9); c.px('c', 13, 13)

def i_snow(c):
    """❄ snö — kristall"""
    c.line('w', 8, 2, 8, 14)
    c.line('w', 4, 4, 12, 12)
    c.line('w', 12, 4, 4, 12)
    c.px('d', 8, 4); c.px('d', 8, 12)
    c.px('d', 5, 5); c.px('d', 11, 11)
    c.px('G', 8, 3); c.px('G', 4, 5)

def i_sun(c):
    """☀ sol — guld med strålar"""
    c.disc('G', 8, 8, 3)
    c.disc('g', 8, 8, 2)
    for (dx, dy) in [(-6,0),(6,0),(0,-6),(0,6),(-4,-4),(4,-4),(-4,4),(4,4)]:
        c.px('G', 8+dx, 8+dy)
    c.px('k', 8, 8)

def i_moon(c):
    """🌒 måne — skära med benkant"""
    c.disc('G', 8, 8, 5)
    c.disc('k', 11, 7, 5)
    c.disc('k', 11, 8, 5)
    # runda vänsterkanten (ljus sida)
    c.px('G', 3, 8); c.px('G', 4, 6); c.px('G', 4, 10)
    c.px('G', 5, 5); c.px('G', 5, 11); c.px('G', 6, 4); c.px('G', 6, 12)
    c.px('w', 4, 7); c.px('w', 4, 9); c.px('w', 5, 6); c.px('w', 5, 10)

def i_star(c):
    """✨ stjärnstoft — gnistra"""
    c.diamond('G', 6, 6, 2)
    c.px('w', 6, 6)
    c.px('G', 11, 4); c.px('G', 12, 5)
    c.px('G', 10, 11); c.px('G', 11, 12)
    c.px('g', 4, 11); c.px('g', 5, 12)

def i_spark(c):
    """⚡ status — blixt (mindre, för text)"""
    c.tri('G', 8, 2, 4, 10, 8, 10)
    c.tri('g', 8, 2, 7, 10, 8, 10)
    c.tri('G', 8, 7, 12, 14, 8, 14)
    c.tri('g', 8, 7, 9, 14, 8, 14)

# ══════════════════════════════════════════════════════════════
#  BATCH 2 — användare, föremål, fiender, status
# ══════════════════════════════════════════════════════════════
def i_user(c):
    """👤 spelare — byst ben/mörk"""
    c.disc('w', 8, 4, 2)
    c.px('G', 7, 3)
    c.tri('w', 3, 12, 13, 12, 8, 7)
    c.tri('k', 4, 12, 12, 12, 8, 8)
    c.px('w', 8, 5)

def i_search(c):
    """🔍 sök — guld-lupp"""
    for x, y in [(4,7),(10,7),(7,4),(7,10),(5,5),(9,5),(5,9),(9,9),(4,6),(4,8),(10,6),(10,8),(6,4),(8,4),(6,10),(8,10)]:
        c.px('G', x, y)
    c.px('k', 7, 7)
    c.px('G', 5, 5)
    c.line('s', 10, 10, 13, 13)
    c.px('s', 14, 14) if False else None

def i_potion(c):
    """🧪 dryck — arkan-flaska med guldvätska"""
    c.tri('p', 5, 13, 11, 13, 8, 7)
    c.tri('P', 6, 12, 10, 12, 8, 8)
    c.vline('p', 8, 4, 6)
    c.px('P', 8, 3)
    c.diamond('G', 8, 11, 1)
    c.px('G', 7, 11); c.px('G', 9, 11)
    c.px('w', 8, 4)

def i_dawn(c):
    """🌅 gryning — sol över horisonten"""
    c.disc('G', 8, 10, 3)
    c.px('g', 8, 7)
    c.hline('w', 11, 3, 13)
    c.px('o', 4, 10); c.px('o', 12, 10)
    c.px('G', 6, 9); c.px('G', 10, 9)

def i_card(c):
    """💳 betalning — kort med guldchip"""
    c.rect('i', 3, 6, 10, 6)
    c.fill('k', 4, 7, 8, 4)
    c.px('G', 5, 8); c.px('G', 6, 8); c.px('g', 5, 9); c.px('g', 6, 9)
    c.px('w', 8, 9); c.px('w', 9, 9); c.px('w', 10, 9)
    c.px('w', 8, 10); c.px('w', 9, 10)
    c.px('s', 3, 6)

def i_camera(c):
    """📷 foto — kamera"""
    c.rect('s', 3, 5, 10, 7)
    c.fill('i', 4, 6, 8, 5)
    for x, y in [(6,8),(10,8),(8,6),(8,10),(6,6),(10,6),(6,10),(10,10)]:
        c.px('s', x, y)
    c.px('k', 8, 8)
    c.px('G', 6, 6)
    c.px('G', 10, 5)

def i_voice(c):
    """🗣 röst/TTS — talande huvud + vågor"""
    c.disc('w', 7, 8, 3)
    c.px('k', 7, 8)
    c.px('w', 5, 6); c.px('w', 5, 10)
    c.px('t', 11, 7); c.px('t', 11, 9); c.px('c', 13, 8)

def i_key(c):
    """🔑 nyckel — guldbåge + skaft med tänder"""
    for x, y in [(3,5),(7,5),(5,3),(5,7),(3,3),(7,3),(3,7),(7,7)]:
        c.px('G', x, y)
    c.px('k', 5, 5)
    c.hline('s', 7, 7, 12)
    c.px('s', 11, 8); c.px('s', 12, 8)
    c.px('G', 4, 4)

def i_home(c):
    """🏠 hem — hus med guldtak"""
    c.tri('g', 8, 3, 3, 7, 13, 7)
    c.rect('w', 4, 7, 8, 6)
    c.fill('k', 5, 8, 6, 4)
    c.px('G', 8, 10); c.px('G', 8, 11)
    c.px('G', 6, 9)
    c.px('g', 3, 7); c.px('g', 13, 7)

def i_calendar(c):
    """📅 kalender — blad med röd rubrik"""
    c.rect('w', 3, 5, 10, 8)
    c.px('G', 5, 4); c.px('G', 8, 4); c.px('G', 11, 4)
    c.hline('r', 6, 4, 11)
    c.px('w', 4, 8); c.px('w', 5, 8); c.px('w', 4, 9); c.px('w', 5, 9)
    c.px('w', 8, 8); c.px('w', 9, 8); c.px('w', 11, 9)

def i_idea(c):
    """💡 idé — glödlampa guld"""
    c.disc('G', 8, 6, 3)
    c.px('w', 8, 6)
    c.px('w', 6, 5); c.px('w', 7, 5)
    c.vline('i', 8, 9, 11)
    c.hline('i', 9, 7, 9)
    c.px('g', 5, 6)

def i_library(c):
    """📚 bibliotek — tre böcker"""
    c.rect('R', 4, 4, 7, 3); c.vline('g', 5, 4, 6); c.px('w', 10, 4)
    c.rect('p', 4, 8, 7, 3); c.vline('g', 5, 8, 10); c.px('w', 10, 8)
    c.rect('t', 4, 12, 7, 2); c.vline('g', 5, 12, 13); c.px('w', 10, 12)

def i_balance(c):
    """⚖ rättvisa — våg"""
    c.hline('s', 6, 5, 11)
    c.vline('s', 8, 4, 12)
    c.disc('g', 8, 4, 1)
    c.hline('s', 10, 3, 7); c.px('s', 3, 11); c.px('s', 7, 11)
    c.hline('s', 10, 9, 13); c.px('s', 9, 11); c.px('s', 13, 11)
    c.px('G', 8, 12)

def i_save(c):
    """💾 spara — diskett"""
    c.rect('s', 3, 4, 10, 9)
    c.rect('i', 5, 4, 6, 2)
    c.fill('k', 5, 8, 6, 4)
    c.px('s', 8, 5)
    c.px('G', 5, 9); c.px('G', 6, 9)

def i_globe(c):
    """🌐 värld — jordklot teal"""
    for x, y in [(4,8),(12,8),(8,4),(8,12),(5,5),(6,5),(11,5),(10,5),(5,11),(6,11),(11,11),(10,11),(4,7),(4,9),(12,7),(12,9),(7,4),(9,4),(7,12),(9,12)]:
        c.px('t', x, y)
    c.line('t', 8, 4, 8, 12)
    c.line('t', 4, 8, 12, 8)
    c.px('c', 6, 5)

def i_target(c):
    """🎯 mål — tavla med träff"""
    for x, y in [(4,8),(12,8),(8,4),(8,12),(5,5),(6,5),(11,5),(10,5),(5,11),(6,11),(11,11),(10,11),(4,7),(4,9),(12,7),(12,9),(7,4),(9,4),(7,12),(9,12)]:
        c.px('r', x, y)
    c.disc('w', 8, 8, 2)
    c.disc('r', 8, 8, 1)
    c.px('w', 8, 8)

def i_handshake(c):
    """🤝 allians — två händer i handslag"""
    c.disc('f', 5, 8, 2); c.disc('f', 11, 8, 2)
    c.px('f', 7, 7); c.px('f', 8, 7); c.px('f', 9, 7)
    c.px('f', 7, 9); c.px('f', 8, 9); c.px('f', 9, 9)
    c.px('w', 7, 8); c.px('w', 8, 8); c.px('w', 9, 8)

def i_check(c):
    """✅ bekräfta — guldbock"""
    c.line('G', 4, 8, 7, 11); c.line('G', 7, 11, 12, 5)
    c.line('g', 4, 9, 7, 12); c.line('g', 7, 12, 12, 6)
    c.px('w', 12, 5)

def i_cross(c):
    """❌ neka — rött kors"""
    c.line('r', 4, 4, 12, 12); c.line('r', 12, 4, 4, 12)
    c.px('R', 5, 5); c.px('R', 11, 11); c.px('R', 11, 5); c.px('R', 5, 11)

def i_mute(c):
    """🔇 tyst — horn med kryss"""
    c.tri('w', 3, 9, 6, 6, 7, 10)
    c.px('G', 5, 7)
    c.line('r', 10, 6, 14, 10); c.line('r', 14, 6, 10, 10)

def i_book(c):
    """📕 bok — sluten codex blodröd"""
    c.rect('R', 4, 4, 8, 8)
    c.rect('r', 5, 5, 6, 6)
    c.vline('g', 8, 4, 12)
    c.px('w', 4, 5); c.px('w', 4, 10)

def i_paper(c):
    """📄 dokument — pergament med veck"""
    c.rect('w', 4, 3, 8, 10)
    c.px('w', 11, 3); c.px('w', 12, 4); c.px('w', 12, 5)
    c.hline('d', 6, 5, 10); c.hline('d', 8, 5, 10); c.hline('d', 10, 5, 8)
    c.px('G', 4, 3)

def i_folder(c):
    """📂 mapp — flik + pärm"""
    c.rect('g', 4, 4, 4, 2)
    c.rect('w', 3, 6, 10, 6)
    c.fill('k', 4, 7, 8, 4)
    c.px('G', 4, 6)

def i_inbox(c):
    """📥 inkorg — fat med pil ned"""
    c.hline('w', 4, 4, 12); c.vline('w', 4, 4, 11); c.vline('w', 12, 4, 11)
    c.hline('w', 11, 3, 13)
    c.vline('G', 8, 5, 7); c.diamond('G', 8, 8, 1)
    c.px('d', 4, 11); c.px('d', 12, 11)

def i_party(c):
    """🎉 fest — baner + konfetti"""
    c.vline('s', 4, 3, 9)
    c.tri('r', 5, 4, 10, 5, 5, 7)
    c.px('G', 12, 4); c.px('p', 11, 8); c.px('t', 13, 6); c.px('w', 12, 11); c.px('r', 9, 12)

def i_fullmoon(c):
    """🌑 fullmåne — mörk med kratrar"""
    c.disc('d', 8, 8, 5)
    c.disc('i', 8, 8, 4)
    c.px('k', 6, 6); c.px('k', 10, 9); c.px('k', 7, 11)
    c.px('w', 5, 5)

def i_village(c):
    """🏘 by — två hus"""
    c.tri('g', 4, 4, 1, 8, 7, 8)
    c.rect('w', 1, 8, 6, 5)
    c.px('k', 3, 11); c.px('G', 5, 9)
    c.tri('g', 12, 6, 9, 9, 15, 9)
    c.rect('i', 9, 9, 6, 3)
    c.px('G', 11, 10)

def i_walk(c):
    """🚶 gå — vandrare"""
    c.px('w', 8, 3); c.px('w', 8, 4); c.px('w', 8, 5)
    c.px('w', 7, 6); c.px('w', 8, 6); c.px('w', 9, 6)
    c.px('w', 8, 7); c.px('w', 8, 8)
    c.line('w', 8, 8, 6, 12); c.line('w', 8, 8, 10, 12)
    c.px('w', 5, 10); c.px('w', 6, 10)
    c.px('d', 6, 11); c.px('d', 10, 11)

def i_boots(c):
    """🥾 stövlar — läderkänga"""
    c.fill('b', 6, 3, 3, 6)
    c.fill('b', 4, 9, 6, 2)
    c.hline('B', 11, 4, 9)
    c.px('G', 5, 9)
    c.px('d', 6, 3)

def i_road(c):
    """🛤 stig — spår med sliper"""
    c.line('s', 5, 3, 4, 12); c.line('s', 11, 3, 12, 12)
    c.hline('b', 5, 5, 11); c.hline('b', 7, 5, 11)
    c.hline('b', 9, 5, 11); c.hline('b', 11, 5, 11)

def i_clock(c):
    """🕰 ur — klocka med visare"""
    for x, y in [(4,8),(12,8),(8,4),(8,12),(5,5),(6,5),(11,5),(10,5),(5,11),(6,11),(11,11),(10,11),(4,7),(4,9),(12,7),(12,9),(7,4),(9,4),(7,12),(9,12)]:
        c.px('g', x, y)
    c.vline('w', 8, 5, 8); c.hline('w', 8, 8, 11)
    c.px('g', 8, 8)

def i_window(c):
    """🪟 fönster — båge med kors"""
    c.rect('w', 4, 3, 8, 8)
    c.fill('k', 5, 4, 6, 6)
    c.vline('w', 8, 4, 10); c.hline('w', 7, 5, 10)
    c.px('G', 5, 4)

def i_music(c):
    """🎵 musik — noter"""
    c.px('w', 4, 10); c.px('w', 4, 11); c.px('w', 5, 11)
    c.vline('w', 5, 5, 10)
    c.px('w', 6, 6); c.px('w', 7, 7)
    c.px('w', 10, 9); c.px('w', 10, 11); c.px('w', 11, 11)
    c.vline('w', 11, 5, 10)

def i_dagger(c):
    """🗡 dolk — stålblad, guldvakt"""
    c.tri('s', 8, 2, 6, 8, 10, 8)
    c.line('w', 7, 3, 7, 7)
    c.hline('g', 9, 6, 10)
    c.vline('b', 8, 10, 11)
    c.px('G', 8, 12)
    c.px('w', 9, 3)

def i_axe(c):
    """🪓 yxa — stålhuvud, träskaft"""
    c.tri('s', 8, 3, 5, 8, 11, 8)
    c.line('w', 7, 4, 6, 7)
    c.line('b', 8, 8, 8, 12)
    c.px('B', 7, 12); c.px('B', 9, 12)
    c.px('G', 6, 4)

def i_bow(c):
    """🏹 båge — spänd med pil"""
    c.px('b', 4, 4); c.px('b', 5, 5); c.px('b', 6, 6)
    c.px('b', 6, 10); c.px('b', 5, 11); c.px('b', 4, 12)
    c.vline('w', 3, 4, 12)
    c.hline('s', 8, 7, 11)
    c.px('G', 12, 8)
    c.px('w', 7, 7); c.px('w', 7, 9)

def i_fist(c):
    """👊 knytnäve — slag"""
    c.disc('f', 8, 7, 3)
    c.px('f', 6, 5); c.px('f', 8, 5); c.px('f', 10, 5)
    c.px('f', 5, 8); c.px('f', 11, 8)
    c.px('d', 6, 9); c.px('d', 8, 9); c.px('d', 10, 9)

def i_blood(c):
    """🩸 blod — droppe"""
    c.tri('r', 8, 3, 6, 7, 10, 7)
    c.disc('r', 8, 8, 2)
    c.px('G', 7, 4)
    c.px('R', 8, 9)

def i_clip(c):
    """📎 gem — pappersklämma"""
    c.line('s', 5, 3, 5, 12); c.line('s', 5, 12, 9, 12)
    c.line('s', 9, 12, 9, 5); c.line('s', 9, 5, 7, 5); c.line('s', 7, 5, 7, 10)
    c.px('G', 5, 3)

def i_picture(c):
    """🖼 tavla — ram med berg"""
    c.rect('g', 3, 3, 10, 10)
    c.rect('k', 4, 4, 8, 8)
    c.tri('w', 5, 10, 8, 5, 11, 10)
    c.px('G', 11, 5)

def i_eye(c):
    """👁 öga — vakande blick"""
    c.px('w', 4, 7); c.px('w', 5, 6); c.px('w', 6, 5); c.px('w', 10, 5)
    c.px('w', 11, 6); c.px('w', 12, 7)
    c.px('w', 4, 9); c.px('w', 5, 10); c.px('w', 6, 11); c.px('w', 10, 11)
    c.px('w', 11, 10); c.px('w', 12, 9)
    c.disc('p', 8, 8, 2)
    c.px('k', 8, 8)
    c.px('P', 7, 7)

def i_castle(c):
    """🏰 slott — torn med tinnar"""
    c.px('g', 3, 3); c.px('g', 4, 3); c.px('g', 6, 3); c.px('g', 7, 3)
    c.px('g', 9, 3); c.px('g', 10, 3); c.px('g', 12, 3); c.px('g', 13, 3)
    c.vline('g', 3, 4, 7); c.vline('g', 4, 4, 7)
    c.vline('g', 12, 4, 7); c.vline('g', 13, 4, 7)
    c.hline('g', 4, 5, 11); c.hline('g', 7, 5, 11)
    c.fill('s', 5, 5, 6, 2)
    c.px('k', 7, 6); c.px('k', 8, 6); c.px('k', 7, 7); c.px('k', 8, 7)
    c.px('G', 6, 5)

def i_shield(c):
    """🛡 sköld — stål med guldband"""
    c.tri('s', 8, 2, 3, 7, 8, 14)
    c.tri('s', 8, 2, 13, 7, 8, 14)
    c.tri('i', 8, 4, 4, 7, 8, 13)
    c.tri('i', 8, 4, 12, 7, 8, 13)
    c.vline('g', 8, 4, 12)
    c.px('G', 8, 3)
    c.px('w', 5, 4); c.px('w', 5, 5)
    c.px('d', 11, 11)

def i_trash(c):
    """🗑 papperskorg — med lock och streck"""
    c.hline('s', 3, 5, 11)
    c.rect('s', 4, 5, 8, 8)
    c.hline('s', 12, 3, 13)
    c.vline('i', 6, 6, 11); c.vline('i', 8, 6, 11); c.vline('i', 10, 6, 11)
    c.px('G', 5, 5)

def i_boar(c):
    """🐗 vildsvin — huvud med betar"""
    c.disc('b', 8, 7, 4)
    c.disc('B', 8, 8, 2)
    c.px('k', 7, 5); c.px('k', 9, 5)
    c.px('k', 7, 8); c.px('k', 9, 8)
    c.px('w', 6, 10); c.px('w', 10, 10)
    c.px('w', 5, 9); c.px('w', 11, 9)
    c.px('G', 6, 5)

def i_wolf(c):
    """🐺 varg — huvud som ylar"""
    c.tri('s', 8, 2, 4, 7, 12, 7)
    c.tri('d', 8, 3, 5, 7, 11, 7)
    c.px('r', 6, 5); c.px('r', 10, 5)
    c.tri('s', 8, 7, 6, 10, 10, 10)
    c.px('w', 7, 10); c.px('w', 9, 10)
    c.px('r', 8, 9)
    c.px('w', 5, 2); c.px('w', 11, 2)

def i_snake(c):
    """🐍 orm — ringlad med tunga"""
    for x, y in [(5,10),(11,10),(8,7),(8,13),(6,8),(10,8),(6,12),(10,12),(5,9),(5,11),(11,9),(11,11),(7,7),(9,7),(7,13),(9,13)]:
        c.px('n', x, y)
    c.disc('n', 8, 5, 2)
    c.px('k', 7, 5); c.px('k', 9, 5)
    c.px('r', 8, 3); c.px('r', 9, 2); c.px('r', 10, 2)
    c.px('G', 6, 5)

def i_spider(c):
    """🕷 spindel — med blodögon"""
    c.px('i', 4, 4); c.px('i', 3, 5); c.px('i', 4, 7); c.px('i', 3, 8)
    c.px('i', 12, 4); c.px('i', 13, 5); c.px('i', 12, 7); c.px('i', 13, 8)
    c.px('i', 5, 5); c.px('i', 5, 7); c.px('i', 11, 5); c.px('i', 11, 7)
    c.disc('i', 8, 6, 1)
    c.disc('i', 8, 9, 2)
    c.px('r', 7, 5); c.px('r', 9, 5)

def i_bat(c):
    """🦇 fladdermus — utbredda vingar"""
    c.tri('R', 6, 7, 1, 5, 3, 11)
    c.tri('R', 10, 7, 15, 5, 13, 11)
    c.px('r', 5, 6); c.px('r', 11, 6)
    c.px('R', 7, 6); c.px('R', 8, 6); c.px('R', 9, 6); c.px('R', 8, 7); c.px('R', 8, 8)
    c.px('R', 7, 5); c.px('R', 9, 5)
    c.px('r', 7, 7); c.px('r', 9, 7)
    c.px('w', 7, 9); c.px('w', 9, 9)

def i_ogre(c):
    """👹 ogre — demonansikte"""
    c.disc('R', 8, 8, 4)
    c.disc('r', 8, 8, 3)
    c.px('w', 5, 4); c.px('w', 6, 3); c.px('w', 11, 4); c.px('w', 10, 3)
    c.px('k', 6, 6); c.px('k', 10, 6)
    c.px('r', 6, 5); c.px('r', 10, 5)
    c.px('R', 8, 8)
    c.hline('k', 10, 6, 10)
    c.px('w', 7, 10); c.px('w', 9, 10)

def i_zombie(c):
    """🧟 zombie — grönt huvud med ärr"""
    c.disc('N', 8, 7, 4)
    c.px('n', 6, 6); c.px('n', 10, 6)
    c.px('k', 6, 6); c.px('k', 10, 6)
    c.px('r', 6, 5); c.px('r', 10, 5)
    c.px('k', 7, 9); c.px('k', 8, 9); c.px('k', 9, 9)
    c.px('d', 5, 4); c.px('d', 6, 4)
    c.px('N', 7, 3); c.px('N', 8, 3); c.px('N', 9, 3)

def i_rat(c):
    """🐀 råtta — med rosa svans"""
    c.disc('s', 9, 5, 2)
    c.disc('s', 8, 9, 2)
    c.disc('d', 7, 4, 1)
    c.px('k', 9, 5)
    c.px('r', 11, 4)
    c.line('p', 7, 10, 4, 12)
    c.px('p', 4, 12); c.px('p', 3, 12)
    c.px('G', 10, 5)

def i_scorpion(c):
    """🦂 skorpion — med gadd"""
    c.px('s', 7, 10); c.px('s', 8, 10); c.px('s', 9, 10)
    c.px('s', 8, 9); c.px('s', 8, 8)
    c.px('s', 5, 8); c.px('s', 6, 8); c.px('s', 6, 9)
    c.px('s', 11, 8); c.px('s', 10, 8); c.px('s', 10, 9)
    c.px('s', 9, 9); c.px('s', 10, 7); c.px('s', 11, 6); c.px('s', 12, 5)
    c.px('r', 12, 4)
    c.px('r', 8, 7)

def i_oni(c):
    """👺 oni — röd demonmask"""
    c.disc('R', 8, 8, 4)
    c.disc('r', 8, 9, 3)
    c.px('w', 5, 3); c.px('w', 6, 2); c.px('w', 11, 3); c.px('w', 10, 2)
    c.px('k', 6, 7); c.px('k', 10, 7)
    c.disc('R', 8, 9, 1)
    c.hline('k', 11, 6, 10)
    c.px('w', 6, 10); c.px('w', 10, 10)
    c.px('w', 7, 12); c.px('w', 9, 12)

def i_question(c):
    """❓ fråga — guld-?"""
    c.hline('G', 3, 5, 9)
    c.px('G', 10, 4); c.px('G', 10, 5)
    c.px('G', 9, 6); c.px('G', 8, 7); c.px('G', 7, 8); c.px('G', 7, 9)
    c.px('G', 7, 11)
    c.px('g', 4, 3)

def i_scroll(c):
    """📜 skriftrulle — pergament med rullar"""
    c.hline('g', 3, 4, 11)
    c.rect('w', 5, 4, 6, 8)
    c.hline('g', 12, 4, 11)
    c.hline('d', 6, 6, 9); c.hline('d', 8, 6, 9); c.hline('d', 10, 6, 8)
    c.px('G', 5, 4)

def i_mirror(c):
    """🪞 spegel — oval med skaft"""
    for x, y in [(5,6),(11,6),(8,3),(8,9),(6,4),(10,4),(6,8),(10,8),(5,5),(5,7),(11,5),(11,7),(7,3),(9,3),(7,9),(9,9)]:
        c.px('s', x, y)
    c.px('k', 8, 6)
    c.px('P', 7, 5)
    c.vline('b', 8, 9, 11)
    c.px('b', 7, 11); c.px('b', 9, 11)

def i_ghost(c):
    """👻 spöke — vålnad med vågig fåll"""
    c.disc('w', 8, 6, 3)
    c.tri('w', 5, 7, 11, 7, 8, 12)
    c.px('w', 4, 11); c.px('w', 5, 12); c.px('w', 6, 11); c.px('w', 7, 12)
    c.px('w', 8, 11); c.px('w', 9, 12); c.px('w', 10, 11); c.px('w', 11, 12)
    c.px('k', 6, 6); c.px('k', 10, 6)
    c.px('k', 7, 8); c.px('k', 8, 8); c.px('k', 9, 8)
    c.px('G', 6, 4)

def i_dove(c):
    """🕊 duva — fredsfågel med olivkvist"""
    c.px('w', 4, 10); c.px('w', 5, 9); c.px('w', 6, 8); c.px('w', 7, 7)
    c.px('w', 8, 6); c.px('w', 9, 5)
    c.px('w', 9, 4); c.px('w', 10, 4)
    c.px('w', 5, 6); c.px('w', 6, 5); c.px('w', 7, 4); c.px('w', 8, 4)
    c.px('n', 10, 6); c.px('n', 11, 6); c.px('n', 12, 5); c.px('n', 11, 7)
    c.px('w', 3, 11); c.px('w', 4, 11)

# ══════════════════════════════════════════════════════════════
#  FIXTURER
# ══════════════════════════════════════════════════════════════
ICONS = {
    'menu':     (i_menu,     '☰'),
    'codex':    (i_codex,    '📖'),
    'gear':     (i_gear,     '⚙'),
    'dice':     (i_dice,     '🎲'),
    'quill':    (i_quill,    '✍'),
    'mask':     (i_mask,     '🎭'),
    'battle':   (i_battle,   '⚔'),
    'quest':    (i_quest,    '⚑'),
    'map':      (i_map,      '🗺'),
    'pin':      (i_pin,      '📌'),
    'npc':      (i_npc,      '🧝'),
    'bag':      (i_bag,      '🎒'),
    'brain':    (i_brain,    '🧠'),
    'crown':    (i_crown,    '👑'),
    'horn':     (i_horn,     '🔊'),
    'refresh':  (i_refresh,  '🔄'),
    'door':     (i_door,     '🚪'),
    'cli':      (i_cli,      '🖥'),
    'engine':   (i_engine,   '🛠'),
    'bolt':     (i_bolt,     '⚡'),
    'stats':    (i_stats,    '📊'),
    'chat':     (i_chat,     '💬'),
    'chest':    (i_chest,    '📦'),
    'palette':  (i_palette,  '🎨'),
    'lock':     (i_lock,     '🔒'),
    'skull':    (i_skull,    '💀'),
    'warn':     (i_warn,     '⚠'),
    'feather':  (i_feather,  '🪶'),
    'owl':      (i_owl,      '🦉'),
    'wizard':   (i_wizard,   '🧙'),
    'dm':       (i_dm,       '🧙‍♂️'),
    'heart':    (i_heart,    '❤'),
    'coin':     (i_coin,     '🪙'),
    'torch':    (i_torch,    '🕯'),
    'fire':     (i_fire,     '🔥'),
    'leaf':     (i_leaf,     '🌿'),
    'tree':     (i_tree,     '🌲'),
    'mountain': (i_mountain, '⛰'),
    'water':    (i_water,    '🌊'),
    'snow':     (i_snow,     '❄'),
    'sun':      (i_sun,      '☀'),
    'moon':     (i_moon,     '🌒'),
    'star':     (i_star,     '✨'),
    'spark':    (i_spark,    '⚡'),
    'user':     (i_user,     '👤'),
    'search':   (i_search,   '🔍'),
    'potion':   (i_potion,   '🧪'),
    'dawn':     (i_dawn,     '🌅'),
    'card':     (i_card,     '💳'),
    'camera':   (i_camera,   '📷'),
    'voice':    (i_voice,    '🗣'),
    'key':      (i_key,      '🔑'),
    'home':     (i_home,     '🏠'),
    'calendar': (i_calendar, '📅'),
    'idea':     (i_idea,     '💡'),
    'library':  (i_library,  '📚'),
    'balance':  (i_balance,  '⚖'),
    'save':     (i_save,     '💾'),
    'globe':    (i_globe,    '🌐'),
    'target':   (i_target,   '🎯'),
    'handshake':(i_handshake,'🤝'),
    'check':    (i_check,    '✅'),
    'cross':    (i_cross,    '❌'),
    'mute':     (i_mute,     '🔇'),
    'book':     (i_book,     '📕'),
    'paper':    (i_paper,    '📄'),
    'folder':   (i_folder,   '📂'),
    'inbox':    (i_inbox,    '📥'),
    'party':    (i_party,    '🎉'),
    'fullmoon': (i_fullmoon, '🌑'),
    'village':  (i_village,  '🏘'),
    'walk':     (i_walk,     '🚶'),
    'boots':    (i_boots,    '🥾'),
    'road':     (i_road,     '🛤'),
    'clock':    (i_clock,    '🕰'),
    'window':   (i_window,   '🪟'),
    'music':    (i_music,    '🎵'),
    'dagger':   (i_dagger,   '🗡'),
    'axe':      (i_axe,      '🪓'),
    'bow':      (i_bow,      '🏹'),
    'fist':     (i_fist,     '👊'),
    'blood':    (i_blood,    '🩸'),
    'clip':     (i_clip,     '📎'),
    'picture':  (i_picture,  '🖼'),
    'eye':      (i_eye,      '👁'),
    'castle':   (i_castle,   '🏰'),
    'shield':   (i_shield,   '🛡'),
    'trash':    (i_trash,    '🗑'),
    'boar':     (i_boar,     '🐗'),
    'wolf':     (i_wolf,     '🐺'),
    'snake':    (i_snake,    '🐍'),
    'spider':   (i_spider,   '🕷'),
    'bat':      (i_bat,      '🦇'),
    'ogre':     (i_ogre,     '👹'),
    'zombie':   (i_zombie,   '🧟'),
    'rat':      (i_rat,      '🐀'),
    'scorpion': (i_scorpion, '🦂'),
    'oni':      (i_oni,      '👺'),
    'question': (i_question, '❓'),
    'scroll':   (i_scroll,   '📜'),
    'mirror':   (i_mirror,   '🪞'),
    'ghost':    (i_ghost,    '👻'),
    'dove':     (i_dove,     '🕊'),
}

# Alias: flera emojis → samma sigil (t.ex. 💰→mynt, ✏→penna)
EXTRA_MAP = {
    '💰': 'coin', '⭐': 'star', '🌙': 'moon', '🌑': 'fullmoon',
    '🗝': 'key', '🕯': 'torch', '❤️': 'heart', '❤': 'heart',
    '🖊': 'quill', '✏': 'quill', '🖋': 'quill', '✍': 'quill',
    '🧙♂️': 'dm', '🧙♂': 'dm', '🧙🏽♂️': 'dm',
    '⚔️': 'battle', '🛡️': 'shield', '🔒': 'lock', '💀': 'skull',
    '⚡': 'bolt', '🔥': 'fire', '🕷': 'spider', '💯': 'target',
    '📈': 'stats', '📉': 'stats', '⚕': 'potion', '💊': 'potion',
    '🏷': 'pin', '📍': 'pin', '📝': 'paper', '🗒': 'paper',
    '📋': 'paper', '🗂': 'folder', '🖥': 'cli', '💻': 'cli',
    '🌄': 'dawn', '🌇': 'dawn', '☀️': 'sun', '🌞': 'sun',
    '🌙': 'moon', '🌟': 'star', '💫': 'star', '🪄': 'wizard',
    '🗡️': 'dagger', '⚔': 'battle', '🏹': 'bow', '🪓': 'axe',
    '🔮': 'potion', '⚗': 'potion', '🧪': 'potion',
    '👑': 'crown', '🦉': 'owl', '🧠': 'brain', '📊': 'stats',
    '💬': 'chat', '🗨': 'chat', '📦': 'chest', '🎁': 'chest',
    '🎨': 'palette', '🖌': 'palette', '✒': 'quill',
    '⚠️': 'warn', '🪶': 'feather', '📖': 'codex', '📕': 'book',
    '📚': 'library', '⚙️': 'gear', '☰': 'menu', '🎲': 'dice',
    '🎭': 'mask', '⚑': 'quest', '🗺': 'map', '🧝': 'npc',
    '🎒': 'bag', '🔄': 'refresh', '🚪': 'door', '🔊': 'horn',
    '🔔': 'horn', '🛠': 'engine', '🔧': 'engine', '⚒': 'engine',
    '🌿': 'leaf', '🌲': 'tree', '⛰': 'mountain', '🌊': 'water',
    '❄': 'snow', '🌨': 'snow', '⛄': 'snow', '🌬': 'water',
    '🚶': 'walk', '🏃': 'walk', '🥾': 'boots', '🛤': 'road',
    '🕰': 'clock', '⏰': 'clock', '🪟': 'window', '🎵': 'music',
    '🎶': 'music', '🎵': 'music', '🗣': 'voice', '🔊': 'horn',
    '🤝': 'handshake', '✅': 'check', '❌': 'cross', '⛔': 'cross',
    '📷': 'camera', '📸': 'camera', '🗑': 'trash', '🗃': 'trash',
    '🖼': 'picture', '🖺': 'picture', '👁': 'eye', '🧿': 'eye',
    '🏰': 'castle', '🌫': 'mountain', '🌾': 'leaf',
    '☠': 'skull', '🏔': 'mountain', '🏁': 'quest', '🧭': 'globe',
    '🌌': 'star', '💥': 'fire', '📤': 'inbox', '💪': 'fist',
    '💔': 'heart', '💜': 'heart', '💚': 'heart', '📁': 'folder',
    '🤖': 'engine', '❓': 'question', '❔': 'question', '📜': 'scroll',
    '🪞': 'mirror', '👻': 'ghost', '📃': 'scroll', '🕸': 'spider',
    '🏴': 'quest', '🚩': 'quest',
    '🌍': 'globe', '🌎': 'globe', '🌏': 'globe', '🖤': 'heart',
    '💞': 'heart', '📡': 'globe', '🚨': 'warn', '💭': 'chat',
    '📧': 'paper', '🕊': 'dove', '💟': 'heart', '😤': 'fist',
}

def build(name):
    c = Canvas()
    fn, emoji = ICONS[name]
    fn(c)
    return c

# ══════════════════════════════════════════════════════════════
#  EMIT: sprites.js v2
# ══════════════════════════════════════════════════════════════
RENDERER = r'''/**
 * sprites.js v2 — Terminal-sigils (16×16 originaldesigner)
 * ------------------------------------------------------------------
 * Riktiga ikoner, INGA emoji-kopior. Genererad av tools/spriteforge.py.
 * Semantiska namn + emoji-mappning: UI anropar SPR.icon('codex'),
 * dynamiskt innehåll mappas automatiskt (emoji → sigil).
 */
const SPR = (() => {
  const PAL = __PAL__;
  const GRID = __GRID__;
  const EMOJI_MAP = __EMOJI_MAP__;

  // Text-symboler som får vara kvar (monokroma, ser redan CLI ut)
  const KEEP = new Set(['✦','✕','✓','♀','♫','♪','⚜','♂','❯','➤','✚','✛','✗','✎','⚒','⚗','⚄','⚲','♾','🔹','❦','⬇','⬆','➡','⬅','·','—','➕','✷','✧','🜂','🜲','🜍','✉','🜁','🜄','🜃']);

  const EMOJI_RE = /(?:\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F1E6}-\u{1F1FF}... )/gu;
  const EMOJI_RE2 = /(?:[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F1E6}-\u{1F1FF}]\uFE0F?)(?:\u200D[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]\uFE0F?)*/gu;

  const cache = {};

  // ── 16×16 → inline SVG ──
  function svgFor(name) {
    if (cache[name]) return cache[name];
    const key = EMOJI_MAP[name] || name;
    const rows = GRID[key];
    if (!rows) return null;
    const grid = rows.join('');
    let rects = '';
    for (let i = 0; i < 256; i++) {
      const color = PAL[grid[i]];
      if (!color) continue;
      rects += '<rect x="' + (i % 16) + '" y="' + Math.floor(i / 16) +
               '" width="1" height="1" fill="' + color + '"/>';
    }
    cache[name] = '<svg class="pxs" viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">' +
                  rects + '</svg>';
    return cache[name];
  }

  function svgEl(name) {
    const html = svgFor(name);
    if (!html) return null;
    const tpl = document.createElement('template');
    tpl.innerHTML = html;
    return tpl.content.firstChild;
  }

  function baseOf(token) {
    return String.fromCodePoint(token.codePointAt(0));
  }

  // ── Ersätt emojis i en sträng → HTML med sigils ──
  function html(str) {
    return String(str).replace(EMOJI_RE2, (m) => {
      const base = baseOf(m);
      if (KEEP.has(base)) return m;
      const svg = svgFor(m) || svgFor(base);
      return svg || m;
    });
  }

  // ── Explicit ikon (för UI-kod): SPR.icon('codex') → element ──
  function icon(name) {
    return svgEl(name);
  }

  function spritizeTextNode(tn) {
    const val = tn.nodeValue;
    if (!val || !EMOJI_RE2.test(val)) { EMOJI_RE2.lastIndex = 0; return; }
    EMOJI_RE2.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0, m, replaced = false;
    while ((m = EMOJI_RE2.exec(val)) !== null) {
      const base = baseOf(m[0]);
      if (KEEP.has(base)) continue;
      const el = svgEl(m[0]) || svgEl(base);
      if (!el) continue;
      if (m.index > last) frag.appendChild(document.createTextNode(val.slice(last, m.index)));
      frag.appendChild(el);
      last = m.index + m[0].length;
      replaced = true;
    }
    if (!replaced) return;
    if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
    tn.parentNode.replaceChild(frag, tn);
  }

  function spritize(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(spritizeTextNode);
  }

  function init() {
    if (!document.body) return;
    spritize(document.body);
    const obs = new MutationObserver(muts => {
      muts.forEach(m => {
        m.addedNodes.forEach(nd => {
          if (nd.nodeType === 3) spritizeTextNode(nd);
          else if (nd.nodeType === 1) spritize(nd);
        });
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { html, spritize, svgFor, icon };
})();
'''

def emit_js(out_path):
    pal_js = json.dumps(PAL, ensure_ascii=False)
    grid_js = {}
    emoji_map = {}
    for name, (fn, emoji) in ICONS.items():
        c = build(name)
        grid_js[name] = c.rows()
        emoji_map[emoji] = name
    # alias: flera emojis → samma sigil
    for emoji, name in EXTRA_MAP.items():
        if name not in grid_js:
            raise SystemExit(f"EXTRA_MAP pekar på okänd ikon: {name}")
        emoji_map[emoji] = name
    # extra mappningar: ZWJ/VS16-varianter av DM
    emoji_map['🧙‍♂'] = 'dm'
    emoji_map['🧙🏽‍♂️'] = 'dm'
    # vanliga varianter: ⚔️ / ⚡️ med VS16 etc. hanteras av baseOf-fallback
    grid_js_dump = json.dumps(grid_js, ensure_ascii=False, indent=0)
    emoji_map_dump = json.dumps(emoji_map, ensure_ascii=False)
    js = RENDERER.replace('__PAL__', pal_js).replace('__GRID__', grid_js_dump).replace('__EMOJI_MAP__', emoji_map_dump)
    # fixa trasig regex-rad (placeholder bara i mallen ovan)
    js = js.replace("const EMOJI_RE = /(?:\\u{1F000}-\\u{1FAFF}\\u{2600}-\\u{27BF}\\u{2B00}-\\u{2BFF}\\u{1F1E6}-\\u{1F1FF}... )/gu;\n  ", "")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(js)
    print(f"✓ skrev {out_path} ({len(ICONS)} ikoner)")

# ══════════════════════════════════════════════════════════════
#  EMIT: preview.html
# ══════════════════════════════════════════════════════════════
def emit_preview(out_path):
    sections = [
        ('Nav & System', ['menu','codex','gear','refresh','cli','engine','horn','stats','chat','door','lock','warn']),
        ('Spelar-UI', ['dice','quill','mask','battle','quest','map','pin','npc','bag','brain','crown','palette']),
        ('Kreatur & Mörker', ['skull','wizard','dm','owl','heart','coin','chest','torch','feather','star','spark']),
        ('Natur & Status', ['fire','leaf','tree','mountain','water','snow','sun','moon']),
    ]
    def cell(name, px):
        c = build(name)
        return f'<div class="cell" style="width:{px}px;height:{px}px">{c.svg(px)}</div>'
    cards = []
    for title, names in sections:
        rows = []
        for name in names:
            emoji = ICONS[name][1]
            rows.append(f'''<div class="card">
  <div class="big">{cell(name, 44)}</div>
  <div class="mid">{cell(name, 20)}</div>
  <div class="name">{name}</div>
  <div class="emoji">{emoji}</div>
</div>''')
        cards.append(f'<h2>{title}</h2><div class="grid">{"".join(rows)}</div>')
    # storleksdemo
    sizes = ''.join(f'<span class="sz" style="font-size:{s}px">{build("codex").svg(1)}</span>' for s in (10,12,14,16,18,20,24,32))
    html_doc = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Spriteforge — Mörkrets Rike</title>
<style>
  body{{ background:#0a0a12; color:#e0e0ec; font-family:monospace; padding:24px; }}
  h1{{ color:#e8c65a; font-size:1.4rem; letter-spacing:2px; text-transform:uppercase; }}
  h2{{ color:#a88ae8; font-size:1rem; margin-top:32px; border-bottom:1px solid #2a2a3a; padding-bottom:6px; }}
  .grid{{ display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:12px; margin-top:12px; }}
  .card{{ background:#12121e; border:1px solid #26263a; border-radius:4px; padding:10px; text-align:center; }}
  .big{{ display:flex; justify-content:center; margin-bottom:6px; }}
  .mid{{ display:flex; justify-content:center; margin-bottom:6px; opacity:.8; }}
  .name{{ font-size:.72rem; color:#a8b2c0; }}
  .emoji{{ font-size:.7rem; color:#4a4a6a; margin-top:2px; }}
  .sz{{ display:inline-flex; align-items:center; justify-content:center; width:40px; height:40px; border:1px dashed #26263a; margin:4px; }}
  svg{{ image-rendering:pixelated; }}
</style></head><body>
<h1>✦ Spriteforge — terminal-sigils</h1>
<p style="color:#6a6a80">Originaldesigner 16×16 · guld+ben+arcane · genererad {{__DATE__}}</p>
{"".join(cards)}
<h2>Storlekar (codex-sigil)</h2><div style="margin-top:8px">{sizes}</div>
</body></html>'''
    html_doc = html_doc.replace('__DATE__', __import__('datetime').date.today().isoformat())
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_doc)
    print(f"✓ skrev {out_path}")

if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    emit_js(os.path.join(base, 'frontend', 'sprites.js'))
    emit_preview(os.path.join(base, 'tools', 'sprite-preview.html'))
