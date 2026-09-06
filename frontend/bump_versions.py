#!/usr/bin/env python3
"""bump_versions.py — central cache-busting versioner for frontend/*.html.

Usage:
  python3 bump_versions.py snes.css=41 themes.js=20260906a i18n.js=20260906a [modal.js=20260906a]

Rewrites every `FILE?v=XXX` occurrence (link/script tags AND prose/comments)
across all *.html in this directory to the given value, so all pages ship one
consistent version per asset. Excludes help.html (owned by i18n wave).
"""
import re, sys, pathlib

EXCLUDE = set()  # all *.html incl help.html: version params only (cache-busting contract), no content changes

def main():
    here = pathlib.Path(__file__).resolve().parent
    specs = {}
    for arg in sys.argv[1:]:
        if '=' not in arg:
            sys.exit(f'bad arg {arg!r}, want FILE=VERSION')
        f, v = arg.split('=', 1)
        specs[re.escape(f)] = v
    if not specs:
        sys.exit('no specs')
    changed = []
    for p in sorted(here.glob('*.html')):
        if p.name in EXCLUDE:
            continue
        src = p.read_text(encoding='utf-8')
        out = src
        for esc_file, ver in specs.items():
            out = re.sub(r'(' + esc_file + r'\?v=)[^"\'\s&)]+', r'\g<1>' + ver, out)
        if out != src:
            p.write_text(out, encoding='utf-8')
            changed.append(p.name)
    print('bumped:', ', '.join(changed) or '(none)')

if __name__ == '__main__':
    main()
