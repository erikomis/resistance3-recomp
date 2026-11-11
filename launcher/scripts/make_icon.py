#!/usr/bin/env python3
# Regenerate the placeholder icon: python3 scripts/make_icon.py src-tauri/icons/app-icon.png
# then: npx tauri icon src-tauri/icons/app-icon.png
# An original placeholder (no game art, no logo): a red targeting reticle with
# a double ring (the Resistance 3 launcher; the Resistance: Fall of Man one
# has a single ring) on a dark gunmetal rounded square. Standard library only.
import math, struct, sys, zlib

N = 1024
C = N / 2

def rr(px, py, r=200, m=40):
    x0, y0, x1, y1 = m, m, N - m, N - m
    cx = min(max(px, x0 + r), x1 - r)
    cy = min(max(py, y0 + r), y1 - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r and x0 <= px <= x1 and y0 <= py <= y1

def reticle(px, py):
    """1 where the reticle is drawn: two rings, four ticks with a gap at the
    centre, and a small dot."""
    dx, dy = px - C, py - C
    d = math.hypot(dx, dy)
    if 290 <= d <= 330:                     # the outer ring
        return 1
    if 220 <= d <= 252:                     # the inner ring
        return 1
    if d <= 34:                             # the dot
        return 1
    w = 24                                  # tick half-width
    if abs(dx) <= w and 120 <= abs(dy) <= 410:
        return 1
    if abs(dy) <= w and 120 <= abs(dx) <= 410:
        return 1
    return 0

S = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
rows = []
for y in range(N):
    row = bytearray([0])
    for x in range(N):
        a = b = 0
        for sx, sy in S:
            px, py = x + sx, y + sy
            if rr(px, py):
                a += 1
                b += reticle(px, py)
        if a == 0:
            row += b"\0\0\0\0"
            continue
        t = y / N
        bg = (int(34 - 18 * t), int(36 - 20 * t), int(40 - 22 * t))     # gunmetal, darker below
        # a faint vertical light stripe through the middle
        glow = max(0.0, 1 - abs(x - C) / 420) * 10
        bg = tuple(min(255, int(c + glow)) for c in bg)
        fg = (232, 85, 58)                                              # styles.css --accent
        f = b / a
        col = [int(bg[i] * (1 - f) + fg[i] * f) for i in range(3)]
        row += bytes(col + [int(255 * a / 4)])
    rows.append(bytes(row))

def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
open(sys.argv[1], "wb").write(png)
