"""geo.py: small geometry helpers for the map charts (no extra libraries beyond numpy and matplotlib).

* decode_topology()  reads data/clean/states.topojson back into plain longitude/latitude polygons
* centroid_of_largest_part()  gives each state one sensible point for its symbol
* sample_points_inside()  places dots at random inside a state (for the dot map)
* albers()  the same conic equal-area projection that Vega-Lite draws the maps with,
            used only to give the Dorling cartogram a geographic starting layout
"""
import math
import numpy as np
from matplotlib.path import Path


def decode_topology(topo):
    """Turn TopoJSON (shared, delta-encoded arcs) into a list of states with polygons in lon/lat."""
    scale, translate = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        arcs.append(pts)

    def ring(indices):
        pts = []
        for i in indices:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]   # a negative index means "this arc, reversed"
            pts.extend(a if not pts else a[1:])
        return pts

    states = []
    for obj_name, obj in topo["objects"].items():
        for g in obj["geometries"]:
            polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
            states.append({
                "state": g["properties"]["state"],
                "code_state": g["properties"]["code_state"],
                "region": g["properties"]["region"],
                "polygons": [[ring(r) for r in poly] for poly in polys],   # polygon = [outer ring, hole, hole...]
            })
    return states


def ring_area_centroid(pts):
    """Signed area and centroid of one ring (shoelace formula, planar lon/lat is fine for a label point)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if a == 0:
        return 0.0, pts[0]
    return a, (cx / (6 * a), cy / (6 * a))


def centroid_of_largest_part(state):
    """Centre of the biggest piece of the state (so islands do not drag the symbol into the sea)."""
    best = max(state["polygons"], key=lambda poly: abs(ring_area_centroid(poly[0])[0]))
    return ring_area_centroid(best[0])[1]


def polygon_area(poly):
    outer = abs(ring_area_centroid(poly[0])[0])
    holes = sum(abs(ring_area_centroid(h)[0]) for h in poly[1:])
    return outer - holes


def sample_points_inside(state, n, rng, existing=None, tries=12):
    """n random points inside the state. Each point is the best of `tries` candidates, i.e. the one
    farthest from the points already placed, so dots spread out instead of clumping."""
    polys = state["polygons"]
    weights = np.array([polygon_area(p) for p in polys], dtype=float)
    weights /= weights.sum()
    paths = [(Path(np.array(p[0])), [Path(np.array(h)) for h in p[1:]], np.array(p[0])) for p in polys]
    placed = list(existing or [])
    out = []
    for _ in range(n):
        best, best_d = None, -1.0
        for _ in range(tries):
            k = rng.choice(len(polys), p=weights)
            outer, holes, arr = paths[k]
            lo, hi = arr.min(axis=0), arr.max(axis=0)
            while True:
                pt = lo + rng.random(2) * (hi - lo)
                if outer.contains_point(pt) and not any(h.contains_point(pt) for h in holes):
                    break
            d = min((math.hypot(pt[0] - q[0], pt[1] - q[1]) for q in placed), default=9.0)
            if d > best_d:
                best, best_d = pt, d
        placed.append((best[0], best[1]))
        out.append((best[0], best[1]))
    return out


def albers(lon, lat, parallels=(2.0, 6.0), central_meridian=109.6):
    """Conic equal-area (Albers) projection, same formulas as d3-geo's conicEqualArea:
    parallels [2, 6] and central meridian 109.6 E, i.e. rotate [-109.6, 0, 0]. Returns (x, y) with y pointing UP."""
    y0, y1 = math.radians(parallels[0]), math.radians(parallels[1])
    n = (math.sin(y0) + math.sin(y1)) / 2
    c = 1 + math.sin(y0) * (2 * n - math.sin(y0))
    r0 = math.sqrt(c) / n
    lam = math.radians(lon - central_meridian)
    phi = math.radians(lat)
    r = math.sqrt(c - 2 * n * math.sin(phi)) / n
    return r * math.sin(lam * n), r0 - r * math.cos(lam * n)
