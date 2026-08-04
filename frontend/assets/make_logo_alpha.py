#!/usr/bin/env python3
"""Create assets/logo-cauldron-alpha.png from logo-cauldron.png.

Strategy: flood-fill from the corners over background-like pixels (so only
border-connected background + glow halo become transparent, never interior
art), then map alpha by distance-from-bg with a soft ramp — pure black -> 0,
glow fades in, artwork stays opaque.
"""
import sys, time
import numpy as np
from PIL import Image, ImageDraw

SRC = 'assets/logo-cauldron.png'
DST = 'assets/logo-cauldron-alpha.png'

t0 = time.time()
im = Image.open(SRC).convert('RGB')
w, h = im.size
print(f'{SRC}: {im.size} mode RGB')

# Background color = median of corner patches
corners = []
for (x, y) in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]:
    corners.append(np.array(im.getpixel((x, y))))
bg = np.median(np.array(corners), axis=0).astype(int)
print('bg color:', tuple(bg))

arr = np.array(im).astype(int)
dist = np.abs(arr - bg).sum(axis=2)  # 0..765

# --- connectivity mask: flood-fill source from (0,0) with a sentinel ---
sentinel = (255, 0, 255)
# ensure sentinel doesn't collide with real art colors
near_sentinel = (np.abs(arr - np.array(sentinel)).sum(axis=2) < 12).sum()
if near_sentinel > 0:
    print(f'WARNING: {near_sentinel} pixels near sentinel magenta — picking cyan')
    sentinel = (0, 255, 255)
src = im.copy()
ImageDraw.floodfill(src, (0, 0), sentinel, thresh=130)
pix = np.array(src).astype(int)
flooded = (np.abs(pix - np.array(sentinel)).sum(axis=2) < 12)
print(f'flooded {flooded.mean()*100:.1f}% of image')

# --- alpha: flooded -> ramp 0..255 over [lo, hi]; else opaque ---
alpha = np.full((h, w), 255, dtype=np.uint8)
lo, hi = 45, 130
ramp = np.clip((dist - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
alpha[flooded] = ramp[flooded]

# --- smoke suppression: the source art has a sooty cloud behind the flame
#     (mid-brightness, ABOVE the cauldron rim). On light themes it reads as a
#     dirty smudge; on dark themes it reads as the flame's aura. Same pixels,
#     conflicting goals — cap the aura above the rim at ~28% opacity so it
#     stays a subtle warm glow on every theme. The pot body (below the rim)
#     is never touched.
RIM_Y = 620
above = flooded & (np.arange(h)[:, None] < RIM_Y)
alpha[above] = np.minimum(alpha[above], 72)

# additional gentle fade for non-flooded dim pixels above the rim (glow's
# brighter inner edge / handles), 35%..100% over dist 130..300
smoke = (~flooded) & (np.arange(h)[:, None] < RIM_Y) & (dist >= 130) & (dist < 300)
fade = np.clip(0.35 + 0.65 * (dist[smoke] - 130) / 170.0, 0, 1)
alpha[smoke] = (alpha[smoke] * fade).astype(np.uint8)

out = np.dstack([arr.astype(np.uint8), alpha])
Image.fromarray(out, 'RGBA').save(DST)
chk = Image.open(DST)
print(f'saved {DST}  mode={chk.mode}  ({time.time()-t0:.1f}s)')
print('alpha corner (3,3):', out[3, 3, 3], '| alpha top-mid (512,3):', out[512, 3, 3],
      '| alpha center (512,512):', out[512, 512, 3])
print('alpha==0 fraction:', (alpha == 0).mean() * 100, '%')
print('alpha in (0,255) fraction:', ((alpha > 0) & (alpha < 255)).mean() * 100, '%')
