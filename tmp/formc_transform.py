#!/usr/bin/env python3
"""Track FORM-C transform: login.html + chat.html shape sweep (corrected spec)."""
import re, sys

def sub(s, old, new, n_expected, label):
    c = s.count(old)
    assert c == n_expected, f"{label}: expected {n_expected} got {c} for {old[:70]!r}"
    return s.replace(old, new)

def resub(s, pat, new, n_expected, label):
    s2, c = re.subn(pat, new, s)
    assert c == n_expected, f"{label}: regex {pat!r} expected {n_expected} got {c}"
    return s2

# ─────────────────────────── login.html ───────────────────────────
p = 'frontend/login.html'
s = open(p, encoding='utf-8').read()

# 1. delete private radius vars (legacy softness — spec §1: converge to flat)
s = sub(s, "    --r-card:10px; --r-btn:8px; --r-in:7px;   /* mjuka radier — override-blocket efter snes.css återinför */\n", "", 1, "vars")
# 2. dead var() refs in base rules → drop declarations
s = sub(s, "text-align:center;border-radius:var(--r-btn);transition:transform", "text-align:center;transition:transform", 1, "btn")
s = sub(s, "border:1px solid var(--edge);border-radius:var(--r-card);padding:1rem 1.15rem", "border:1px solid var(--edge);padding:1rem 1.15rem", 1, "tablet")
s = sub(s, "border:1px solid var(--edge);border-radius:var(--r-card);padding:1.15rem", "border:1px solid var(--edge);padding:1.15rem", 1, "ptier")
s = sub(s, "border:1px solid var(--edge);border-radius:var(--r-btn);margin-bottom:.5rem", "border:1px solid var(--edge);margin-bottom:.5rem", 1, "faqdetails")
# 3. f-icon 9px dead base + live !important below → flat (icon tile, not shape-defining)
s = sub(s, "var(--edge));border-radius:9px;color:var(--t-accent", "var(--edge));color:var(--t-accent", 1, "ficon")
# 4. fs-badge 5px dead → token (badge = xs, documentation of intent)
s = sub(s, "border:1px solid var(--gold-bright);border-radius:5px;padding:.34em", "border:1px solid var(--gold-bright);border-radius:var(--radius-xs);padding:.34em", 1, "fsbadge")
# 5. pt-flag dead multi-value → delete
s = sub(s, "padding:.34em .7em;border-radius:0 0 5px 5px}", "padding:.34em .7em}", 1, "ptflag")
# 6. faq scrollbar thumb (pseudo-element = LIVE under reset): 3px → sm token (same value)
s = sub(s, ".faq::-webkit-scrollbar-thumb{background:var(--edge);border-radius:3px}", ".faq::-webkit-scrollbar-thumb{background:var(--edge);border-radius:var(--radius-sm)}", 1, "faqscroll")
# 7. rail-dots: existing pill — normalize 99px→999px (identical render, census-clean)
s = sub(s, "border:1px solid var(--edge);border-radius:99px;padding:.4rem", "border:1px solid var(--edge);border-radius:999px;padding:.4rem", 1, "raildots-base")
# 8. ledger-fold: base said 99px but override rendered it 8px → override dies → flat canon; drop dead decl
s = sub(s, "border:1px solid var(--edge);border-radius:99px;padding:.55rem", "border:1px solid var(--edge);padding:.55rem", 1, "ledgerfold")
# 9. heights §2: input stray 46px → tap-min; gate CTA (large primary) → tap-lg
s = sub(s, ".field input{min-height:46px}", ".field input{min-height:var(--tap-min)}", 1, "input-h")
s = sub(s, ".gate-btn{min-height:46px}", ".gate-btn{min-height:var(--tap-lg)}", 1, "gate-h")
# 10. delete the legacy soft-radius override block; keep pill + rail-arrow transition (non-radius part)
old_block = """/* mjuka radier (snes §0 plattar med * !important) */
.btn,.gate-btn,.field input,.faq details,.ledger-fold{border-radius:var(--r-btn) !important}
.tablet,.ptier,.gate-card,.deck-card,.modal,.ledger-list li.hot,.pile-under{border-radius:var(--r-card) !important}
.deck-abls span,.deck-portrait .corner,.ver-chip,.pt-flag,.ledger-list li .tag,.pitch-list .tag,.hstat,.fs-badge{border-radius:6px !important}
.f-icon{border-radius:9px !important}
.rail-dots{border-radius:99px !important}
.rail-arrow{border-radius:50% !important;transition:border-color .25s,color .25s,background .25s,transform .25s !important}"""
new_block = """/* FORM-C 2026-09-23: mjuka radier raderade — platt är språket (snes §0 global
   reset, spec §1). Levande radier kvar: rail-dots pill (existerande) och
   rail-arrow via .soft-full på elementen (snes.css §.soft). */
.rail-dots{border-radius:999px !important}
.rail-arrow{transition:border-color .25s,color .25s,background .25s,transform .25s !important}"""
s = sub(s, old_block, new_block, 1, "override-block")
# 11. rail-arrow round buttons → sanctioned .soft-full class (spec §1: HTML class edit)
s = sub(s, 'class="rail-arrow prev"', 'class="rail-arrow prev soft-full"', 1, "arrow-prev")
s = sub(s, 'class="rail-arrow next"', 'class="rail-arrow next soft-full"', 1, "arrow-next")

open(p, 'w', encoding='utf-8').write(s)
print("login.html OK")

# ─────────────────────────── chat.html ───────────────────────────
p = 'frontend/chat.html'
s = open(p, encoding='utf-8').read()

# contextual ones first (before global value-equal maps)
s = sub(s, "cursor: pointer; padding: .3rem; border-radius: 6px; }", "cursor: pointer; padding: .3rem; border-radius: var(--radius-sm); }", 1, "cp-close 6px→sm")
s = sub(s, "background: var(--edge); border-radius: 8px; border: 3px solid var(--ink); min-height: 48px;", "background: var(--edge); border-radius: var(--radius-sm); border: 3px solid var(--ink); min-height: 48px;", 1, "scrollbar-thumb 8px→sm (live pseudo; min-height 48px = thumb, not a control)")
s = sub(s, "border-radius: 8px; box-shadow: 0 14px 34px", "border-radius: var(--radius-sm); box-shadow: 0 14px 34px", 1, "tts-pop 8px→sm")
s = sub(s, "border-radius: 8px; pointer-events: none;", "border-radius: var(--radius-xs); pointer-events: none;", 1, "batch-turn 8px→xs")
s = sub(s, "cursor: pointer; border-radius: 8px; transition: all .2s; }", "cursor: pointer; border-radius: var(--radius-sm); transition: all .2s; }", 1, "cp-paint-btn 8px→sm")
s = sub(s, "padding:.9rem 1rem;border-radius:8px;text-decoration:none", "padding:.9rem 1rem;border-radius:var(--radius-md);text-decoration:none", 1, "JS-string CTA 8px→md")
s = sub(s, "border:1px solid var(--edge);color:var(--bone-bright);border-radius:3px;resize:vertical", "border:1px solid var(--edge);color:var(--bone-bright);border-radius:var(--radius-sm);resize:vertical", 1, "avatar-prompt textarea inline 3px→sm")
s = sub(s, "border-radius: 3px !important;", "border-radius: var(--radius-sm) !important;", 2, "scrollbar thumbs 3px!important (existing !imp kept, value tokenized)")

# global value-equal maps (lookahead keeps multi-value shape expressions untouched)
s = resub(s, r"border-radius: 2px(?=\s*[;}])", "border-radius: var(--radius-xs)", 18, "2px→xs")
s = resub(s, r"border-radius: 3px(?=\s*[;}])", "border-radius: var(--radius-sm)", 10, "3px→sm")
s = resub(s, r"border-radius: 4px(?=\s*[;}])", "border-radius: var(--radius-md)", 7, "4px→md")
s = resub(s, r"border-radius: 5px(?=\s*[;}])", "border-radius: var(--radius-sm)", 3, "5px→sm (tts controls)")
s = resub(s, r"border-radius: 6px(?=\s*[;}])", "border-radius: var(--radius-md)", 2, "6px→md (bubble, fb-modal)")
s = resub(s, r"border-radius: 10px(?=\s*[;}])", "border-radius: var(--radius-md)", 4, "10px→md")
s = resub(s, r"border-radius: 12px(?=\s*[;}])", "border-radius: var(--radius-md)", 1, "12px→md")
s = resub(s, r"border-radius: 14px(?=\s*[;}])", "border-radius: var(--radius-md)", 1, "14px→md")

open(p, 'w', encoding='utf-8').write(s)
print("chat.html OK")
