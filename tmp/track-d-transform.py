#!/usr/bin/env python3
"""Track FORM-D shape sweep — revised spec 2026-09-23 (global flat reset canon)."""
import re

BASE = '/home/rostads/dnd-llm/frontend/'
SNES_FILES = ['admin.html','newgame.html','characters.html','help.html','mechanics.html',
              'models.html','pricing.html','releases.html','screenshots.html','reset.html','404.html']

def sc(s, pat, rep, name, log):
    s2, n = re.subn(pat, rep, s)
    if n: log.append(f"{name}: {n}")
    return s2

report = {}
for f in SNES_FILES:
    p = BASE + f
    s = open(p, encoding='utf-8').read()
    orig = s
    log = []
    # ---- targeted height fixes (before blankets) ----
    if f == 'pricing.html':
        s = sc(s, r'\.tier-btn,\.plan-cta\{min-height:48px;display:flex;align-items:center;justify-content:center;min-height:44px;display:flex;align-items:center;justify-content:center;min-height:44px\}',
               '.tier-btn,.plan-cta{min-height:var(--tap-lg);display:flex;align-items:center;justify-content:center}', 'pricing CTA dedup->tap-lg', log)
        s = sc(s, r'\.currency-toggle\{min-height:48px;min-height:44px\}',
               '.currency-toggle{min-height:var(--tap-min)}', 'pricing currency dedup', log)
        s = sc(s, r'\.back,\.currency-toggle\{min-height:44px;min-height:44px;min-height:44px;display:flex;align-items:center;justify-content:center\}',
               '.back,.currency-toggle{min-height:var(--tap-min);display:flex;align-items:center;justify-content:center}', 'pricing back dedup', log)
    if f == 'releases.html':
        s = sc(s, r'\.hist-toggle\{min-height:48px;min-height:44px\}',
               '.hist-toggle{min-height:var(--tap-min)}', 'releases hist-toggle dedup', log)
    if f == 'newgame.html':
        s = sc(s, r'\.scroll-actions select\{width:100%;min-height:48px;',
               '.scroll-actions select{width:100%;min-height:var(--tap-min);', 'newgame select 48->tap-min', log)
        s = sc(s, r'\.pv-reroll\{width:100%;min-height:48px\}',
               '.pv-reroll{width:100%;min-height:var(--tap-min)}', 'newgame pv-reroll 48->tap-min', log)
        s = sc(s, r'\.insp-full \.pv-go\{width:100%;min-height:50px\}',
               '.insp-full .pv-go{width:100%;min-height:var(--tap-lg)}', 'newgame insp pv-go 50->tap-lg', log)
    if f == 'characters.html':
        s = sc(s, r'\.summon-btn\{width:100%;min-height:48px\}',
               '.summon-btn{width:100%;min-height:var(--tap-lg)}', 'chars summon 48->tap-lg', log)
        s = sc(s, r'\.pv-go,\.pv-reroll\{width:100%;min-height:48px\}',
               '.pv-go,.pv-reroll{width:100%;min-height:var(--tap-lg)}', 'chars pvgo pair 48->tap-lg', log)
        s = sc(s, r'\.forge-actions select\{width:100%;min-height:48px\}',
               '.forge-actions select{width:100%;min-height:var(--tap-min)}', 'chars select 48->tap-min', log)
        s = sc(s, r'\.pv-go,\.pv-reroll\{width:100%;min-height:50px\}',
               '.pv-go,.pv-reroll{width:100%;min-height:var(--tap-lg)}', 'chars pvgo pair 50->tap-lg', log)
    if f == 'admin.html':
        # extend the <=640px touch-floor list to inputs + tokenize 44px
        s = sc(s, r'\.act-chip, \.act-btn, \.cap-btn, \.bc-btn, \.pg-btn, \.del-btn, \.cu-btn, \.cbar-more \{\n    min-height: 44px;',
               '.act-chip, .act-btn, .cap-btn, .bc-btn, .pg-btn, .del-btn, .cu-btn, .cbar-more,\n'
               '  .filter-input, .create-user-form input, .create-user-form select, .act-input, .cap-input, .prem-grant select {\n'
               '    min-height: var(--tap-min);', 'admin 640 list extend + tap-min', log)
        # dead 6px panel radii -> DELETE (6px is .soft-class-only per snes.css 2026-09-10
        # rule; dead under global reset so removal is visually inert, converges to flat)
        s = sc(s, r'border-radius: 6px; ', '', 'admin 6px del (mid-line)', log)
        s = sc(s, r' border-radius: 6px;', '', 'admin 6px del (eol)', log)
        # 5px badge spans -> xs (badge/chip intent)
        s = sc(s, r'border-radius:5px', 'border-radius:var(--radius-xs)', 'admin 5px badges->xs', log)
    # ---- blanket radius token mapping (dead literals -> named tokens, same values) ----
    s = sc(s, r'border-radius:(\s*)2px\b', r'border-radius:\1var(--radius-xs)', 'r2->xs', log)
    s = sc(s, r'border-radius:(\s*)3px\b', r'border-radius:\1var(--radius-sm)', 'r3->sm', log)
    s = sc(s, r'border-radius:(\s*)4px\b', r'border-radius:\1var(--radius-md)', 'r4->md', log)
    s = sc(s, r'border-radius:(\s*)50%', r'border-radius:\1var(--radius-full)', 'r50->full', log)
    # ---- blanket 44px min-height tokenization ----
    s = sc(s, r'min-height:(\s*)44px\b', r'min-height:\1var(--tap-min)', 'h44->tap-min', log)
    # ---- gold border pass (border declarations only) ----
    s = sc(s, r'(border[^:;}]*:[^;}]*?)rgba\(201,\s*162,\s*39\s*,\s*', r'\1rgba(var(--gold-rgb),', 'goldborder', log)
    if s != orig:
        open(p, 'w', encoding='utf-8').write(s)
        report[f] = log
    else:
        report[f] = ['NO CHANGES']

# book-souls: border pass ONLY (radii stay — page has no flat reset; heights untouched)
p = BASE + 'book-souls/index.html'
s = open(p, encoding='utf-8').read()
orig = s
log = []
s = sc(s, r'(border[^:;}]*:[^;}]*?)rgba\(201,\s*162,\s*39\s*,\s*', r'\1rgba(var(--gold-rgb),', 'goldborder', log)
if s != orig:
    open(p, 'w', encoding='utf-8').write(s)
report['book-souls/index.html'] = log or ['NO CHANGES']

for f, log in report.items():
    print(f"--- {f}")
    for l in log: print("   ", l)
