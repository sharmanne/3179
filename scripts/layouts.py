"""layouts.py: geometry for the three charts whose shapes Vega-Lite cannot compute itself.

Vega-Lite draws marks where the data says. For the plate, Dorling cartogram and treemap the
"where" is a layout problem, so these routines work it out once, in pixels, and write the result into
data/clean. The charts only DRAW those positions. No data value is changed here: every circle and
rectangle is sized from the real number (circle area, or rectangle area, is proportional to it).
All coordinates: pixels, origin top-left, y pointing down.
"""
import math
import numpy as np


# ---------------------------------------------------------------------------------------------------
# 1. The plate: 100 dots on concentric rings, filled clockwise from 12 o'clock
# ---------------------------------------------------------------------------------------------------
RING_COUNTS = [4, 12, 20, 28, 36]      # 4 + 12 + 20 + 28 + 36 = 100 dots
RING_SPACING = 28                      # px between rings


def plate_cells(cx, cy):
    """Positions of the 100 dots for one plate centred at (cx, cy), sorted clockwise from the top."""
    cells = []
    for k, n in enumerate(RING_COUNTS, start=1):
        radius = RING_SPACING * k
        offset = (math.pi / n) if k % 2 == 0 else 0.0       # stagger every second ring
        for i in range(n):
            theta = 2 * math.pi * i / n + offset              # 0 = straight up, clockwise
            x, y = cx + radius * math.sin(theta), cy - radius * math.cos(theta)
            cells.append({"x": x, "y": y, "ring": k, "angle": theta % (2 * math.pi)})
    cells.sort(key=lambda c: (round(c["angle"], 6), c["ring"]))
    return cells


def largest_remainder(shares, total=100):
    """Round shares (summing to 100) to whole dots that still add up to exactly `total`."""
    floors = {k: math.floor(v) for k, v in shares.items()}
    left = total - sum(floors.values())
    order = sorted(shares, key=lambda k: shares[k] - floors[k], reverse=True)
    for k in order[:left]:
        floors[k] += 1
    return floors


# ---------------------------------------------------------------------------------------------------
# 2. Dorling cartogram: circles nudged apart from their geographic positions
# ---------------------------------------------------------------------------------------------------
def dorling(home, radii, width, height, margin=8.0, gap=3.0, iterations=2500):
    """home = [(x, y), ...] geographic starting points (already in pixels). Returns non-overlapping positions."""
    pos = np.array(home, dtype=float)
    home = np.array(home, dtype=float)
    r = np.array(radii, dtype=float)
    n = len(r)
    for it in range(iterations):
        moved = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                d = pos[j] - pos[i]
                dist = float(np.hypot(*d)) or 1e-6
                need = r[i] + r[j] + gap
                if dist < need:
                    push = (need - dist) / 2
                    # the smaller circle moves more, so big states keep their geographic place
                    wi, wj = r[j] ** 2, r[i] ** 2
                    s = wi + wj
                    pos[i] -= d / dist * push * 2 * wi / s
                    pos[j] += d / dist * push * 2 * wj / s
                    moved += push
        pos += (home - pos) * 0.02                     # gentle pull back to the real location
        pos[:, 0] = np.clip(pos[:, 0], r + margin, width - r - margin)
        pos[:, 1] = np.clip(pos[:, 1], r + margin, height - r - margin)
        if it > 200 and moved < 1e-4:
            break
    return [tuple(p) for p in pos]


def place_labels(xs, ys, radii, inside, names, width, height, char_w=6.6, line_h=15.0, gap=5.0):
    """Label positions for the circles that are too small to hold their own label.
    Tries positions to the right and left of each circle, from the outward-facing side first,
    and keeps the first one that does not touch any circle, any earlier label or the canvas edge.
    Returns label_x, label_y, label_align lists (inside labels are centred on the circle)."""
    n = len(xs)
    cx, cy = sum(xs) / n, sum(ys) / n
    boxes = []
    out_x, out_y, out_a = [None] * n, [None] * n, [None] * n

    def clash(b):
        x0, y0, x1, y1 = b
        if x0 < 0 or x1 > width or y0 < 0 or y1 > height:
            return 1e6
        pen = 0.0
        for k in range(n):
            nx, ny = max(x0, min(xs[k], x1)), max(y0, min(ys[k], y1))
            if math.hypot(nx - xs[k], ny - ys[k]) < radii[k] + 1:
                pen += 1000.0
        for o in boxes:
            if x0 < o[2] and x1 > o[0] and y0 < o[3] and y1 > o[1]:
                pen += 1000.0
        return pen

    order = sorted(range(n), key=lambda i: radii[i], reverse=True)        # big circles choose first
    for i in order:
        if inside[i]:
            out_x[i], out_y[i], out_a[i] = xs[i], ys[i], "center"
            continue
        w = char_w * max(len(names[i]), 9)
        h = 2 * line_h
        outward = math.atan2(ys[i] - cy, xs[i] - cx)
        cands = []
        for deg in range(-60, 61, 15):                                    # right side, then left side
            for side in (1, -1):
                ang = math.radians(deg) if side == 1 else math.radians(180 - deg)
                d_out = abs(math.atan2(math.sin(ang - outward), math.cos(ang - outward)))
                cands.append((d_out, side, ang))
        cands.sort(key=lambda c: c[0])
        best = None
        for d_out, side, ang in cands:
            for extra in (0, 10, 20, 30):
                r = radii[i] + gap + extra
                px, py = xs[i] + r * math.cos(ang), ys[i] + r * math.sin(ang)
                b = (px, py - h / 2, px + w, py + h / 2) if side == 1 else (px - w, py - h / 2, px, py + h / 2)
                score = clash(b) + d_out + extra / 10
                if best is None or score < best[0]:
                    best = (score, px, py, side, b)
                if score < 10:
                    break
            if best[0] < 10:
                break
        _, px, py, side, b = best
        boxes.append(b)
        out_x[i], out_y[i], out_a[i] = px, py, ("left" if side == 1 else "right")
    return out_x, out_y, out_a


# ---------------------------------------------------------------------------------------------------
# 3. Treemap (squarified)
# ---------------------------------------------------------------------------------------------------
def squarify(values, x, y, w, h):
    """Rectangles (x0, y0, x1, y1) with areas proportional to `values` (sorted largest first)."""
    total = float(sum(values))
    scaled = [v * w * h / total for v in values]
    rects = []

    def worst(row, side):
        s = sum(row)
        return max(max(side ** 2 * r / s ** 2, s ** 2 / (side ** 2 * r)) for r in row)

    def layout(row, x, y, w, h):
        s = sum(row)
        if w >= h:                       # lay the row down the left edge
            rw = s / h
            yy = y
            for r in row:
                rects.append((x, yy, x + rw, yy + r / rw)); yy += r / rw
            return x + rw, y, w - rw, h
        rh = s / w                       # lay the row along the top edge
        xx = x
        for r in row:
            rects.append((xx, y, xx + r / rh, y + rh)); xx += r / rh
        return x, y + rh, w, h - rh

    i, row = 0, []
    while i < len(scaled):
        side = min(w, h)
        if not row or worst(row + [scaled[i]], side) <= worst(row, side):
            row.append(scaled[i]); i += 1
        else:
            x, y, w, h = layout(row, x, y, w, h); row = []
    if row:
        layout(row, x, y, w, h)
    return rects
