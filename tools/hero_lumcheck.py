#!/usr/bin/env python3
"""hero_lumcheck.py — assert the login cover art is dark enough where text sits.

Companion to docs/plans/ember-2026-10-22/C-login-and-cover.md §3.6.
Reads a PNG/WebP, crops the *visible* rects (relative to the whole file, because the
art is authored at exactly the painted band size), and checks per-zone luminance.

usage:
  python3 tools/hero_lumcheck.py assets/hero-loreweaver.webp --mode desktop
  python3 tools/hero_lumcheck.py assets/hero-loreweaver-portrait.webp --mode portrait
exit 0 = pass, 1 = fail (thresholds from the brief).
"""
import sys
import numpy as np
from PIL import Image

# zone rects as fractions of the frame: (x0, y0, x1, y1)
ZONES = {
    "desktop": [
        ("text  x0-52 y18-82", (0.00, 0.18, 0.52, 0.82), dict(mean=0.030, p99=0.10, mx=0.15)),
        ("seal  x51-77 y30-72", (0.51, 0.30, 0.77, 0.72), dict(mean=0.12, p99=None, mx=None)),
    ],
    "portrait": [
        ("text  x8-92 y0-60", (0.08, 0.00, 0.92, 0.60), dict(mean=0.020, p99=None, mx=0.08)),
    ],
}


def rel_lum(rgb):
    """WCAG 2.1 relative luminance for an (H,W,3) float array in 0..1 sRGB."""
    c = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def main():
    path = sys.argv[1]
    mode = "desktop"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    img = Image.open(path).convert("RGB")
    W, H = img.size
    a = np.asarray(img, dtype=np.float32) / 255.0
    lum = rel_lum(a)
    print(f"{path}: {W}x{H} (AR {W/H:.3f})  whole-frame mean lum {lum.mean():.4f}")
    ok = True
    for name, (x0, y0, x1, y1), lim in ZONES[mode]:
        sub = lum[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        mean, p99, mx = sub.mean(), float(np.percentile(sub, 99)), sub.max()
        fails = []
        if mean > lim["mean"]:
            fails.append(f"mean {mean:.4f} > {lim['mean']}")
        if lim.get("p99") is not None and p99 > lim["p99"]:
            fails.append(f"p99 {p99:.4f} > {lim['p99']}")
        if lim.get("mx") is not None and mx > lim["mx"]:
            fails.append(f"max {mx:.4f} > {lim['mx']}")
        status = "PASS" if not fails else "FAIL (" + ", ".join(fails) + ")"
        print(f"  {name:22s} mean {mean:.4f}  p99 {p99:.4f}  max {mx:.4f}  -> {status}")
        ok = ok and not fails
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())