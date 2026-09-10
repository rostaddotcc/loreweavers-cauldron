#!/usr/bin/env python3
"""css-brace-check.py — brace-balance gate for frontend CSS.

Scans a CSS file ignoring comments and quoted strings, verifies:
  1. '{' and '}' counts are equal,
  2. nesting depth never goes negative,
  3. file ends at depth 0.
Exit 0 + "GREEN" when balanced; exit 1 + details otherwise.
Usage: python3 scripts/css-brace-check.py frontend/snes.css [...]
"""
import sys


def scan(path: str):
    src = open(path, encoding="utf-8").read()
    depth = 0
    opens = closes = 0
    neg_line = None
    line = 1
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":  # comment
            j = src.find("*/", i + 2)
            if j == -1:
                return path, False, f"unterminated comment from line {line}", opens, closes, depth
            line += src.count("\n", i, j)
            i = j + 2
            continue
        if c in "\"'":  # string
            q = c
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 1
                if i < n and src[i] == "\n":
                    line += 1
                i += 1
            i += 1
            continue
        if c == "{":
            opens += 1
            depth += 1
        elif c == "}":
            closes += 1
            depth -= 1
            if depth < 0 and neg_line is None:
                neg_line = line
        i += 1
    if neg_line is not None:
        return path, False, f"depth went negative at line {neg_line}", opens, closes, depth
    if depth != 0:
        return path, False, f"ends at depth {depth}", opens, closes, depth
    if opens != closes:
        return path, False, "count mismatch", opens, closes, depth
    return path, True, f"balanced ({opens} pairs, end depth 0)", opens, closes, depth


def main():
    ok_all = True
    for p in sys.argv[1:]:
        path, ok, msg, o, c, d = scan(p)
        status = "GREEN" if ok else "RED"
        print(f"{status}: {path} — {msg} [open={o} close={c} final_depth={d}]")
        ok_all &= ok
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
