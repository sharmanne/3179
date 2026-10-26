#!/usr/bin/env python3
"""prepare_data.py: builds every file in data/clean from the untouched files in data/raw.

Run from the site folder:
    python scripts/prepare_data.py
The first run also needs the big FAO file (633 MB, not stored in the repo):
    python scripts/prepare_data.py --fao-full "path/to/FoodBalanceSheets_E_All_Data_(Normalized).csv"

What this script does, and does NOT do
  * It never changes a source value. It only (1) filters rows, (2) joins the two sources by year, (3) averages,
    sums or divides numbers to make the quantities a chart needs, and (4) works out screen positions for the
    four layout-based charts. Every derived column is listed in DATA_SOURCES.md.
  * State names are already identical in the DOSM crops file and the DOSM boundary file, so no name had to be fixed.
  * Numbers are written to 4 decimal places (formatting only).
"""
import argparse, csv, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

import geo
import layouts

SITE = Path(__file__).resolve().parent.parent
RAW, CLEAN = SITE / "data" / "raw", SITE / "data" / "clean"
FAO_EXTRACT = RAW / "FoodBalanceSheets_E_Malaysia.csv"
CROPS_RAW = RAW / "crops_state.csv"
TOPO = CLEAN / "states.topojson"
MALAYSIA_AREA_CODE = "131"

# ---- chart canvases in pixels (the specs use exactly these sizes) -------------------------------------
PLATE_W, PLATE_H = 1000, 470
PLATE_CENTRES = {2010: (190, 250), 2023: (810, 250)}
PLATE_RIM_R = 162
PLATE_FIRST_ROW_Y = 114          # y of the first row of the middle table (9 rows, 34 px apart, centred on the plates)
DORLING_W, DORLING_H = 1000, 470    # canvas; circles are kept inside the top DORLING_AREA_H pixels
DORLING_AREA_H = 440
DORLING_MAX_R = 60                 # radius in pixels of the biggest circle
TREEMAP_W, TREEMAP_H = 520, 400
# C4 tile grid map: one equal square per state, placed roughly where the state is (column, row)
TILE_SIZE, TILE_GAP = 92, 8
TILE_TOP, TILE_LEFT = 20, 8          # pixels of space above and to the left of the grid
TILE_NAME_SPACE = 20                 # room at the top of each square for the state's name
TILES = {"Perlis": (1, 0),
         "Pulau Pinang": (0, 1), "Kedah": (1, 1), "Kelantan": (2, 1), "Terengganu": (3, 1),
         "Perak": (1, 2), "Pahang": (2, 2),
         "Selangor": (0, 3), "W.P. Kuala Lumpur": (1, 3), "Negeri Sembilan": (2, 3),
         "Melaka": (1, 4), "Johor": (2, 4),
         "W.P. Labuan": (5, 1), "Sabah": (6, 1), "Sarawak": (5, 2)}
SHORT_NAMES = {"W.P. Kuala Lumpur": "Kuala Lumpur", "W.P. Labuan": "Labuan"}   # shown on the page without the "W.P." short form


def write(df, name):
    df.to_csv(CLEAN / name, index=False, float_format="%.4f", lineterminator="\n")
    print(f"  wrote data/clean/{name}  ({len(df)} rows, {(CLEAN / name).stat().st_size / 1024:.1f} KB)")


# =====================================================================================================
# 0. RAW FILES
# =====================================================================================================
def make_fao_extract(full_path):
    """Copy only the Malaysia rows (Area Code 131) of the big FAO file into data/raw. Rows are copied as they are."""
    print(f"Reading {full_path} (large file, this takes a minute)...")
    h = hashlib.sha256()
    with open(full_path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    n = 0
    with open(full_path, newline="", encoding="utf-8") as src, open(FAO_EXTRACT, "w", newline="", encoding="utf-8") as dst:
        reader, writer = csv.reader(src), csv.writer(dst, quoting=csv.QUOTE_ALL, lineterminator="\n")
        header = next(reader)
        writer.writerow(header)
        area = header.index("Area Code")
        for row in reader:
            if row[area] == MALAYSIA_AREA_CODE:
                writer.writerow(row)
                n += 1
    print(f"  wrote {FAO_EXTRACT.name}: {n} Malaysia rows. SHA-256 of the full FAO file: {h.hexdigest()}")


def load_fao():
    df = pd.read_csv(FAO_EXTRACT, dtype=str, keep_default_na=False)
    df["code"] = df["Item Code (FBS)"].str.lstrip("'")
    df["Year"] = df["Year"].astype(int)
    df["v"] = pd.to_numeric(df["Value"])
    return df


def fao_series(fao, code, element):
    """One FAO series as {year: value}. element 645 = kg per person per year, 664 = kcal per person per day, 511 = population ('000)."""
    s = fao[(fao["code"] == code) & (fao["Element Code"] == str(element))].set_index("Year")["v"].sort_index()
    assert len(s) == 14, f"{code}/{element}: expected 14 years, found {len(s)}"
    return s


# =====================================================================================================
# 1. FAO CHARTS (C1 plate, C2 dumbbell, C3 heatmap)
# =====================================================================================================
PLATE_GROUPS = ["Rice", "Wheat and other cereals", "Vegetable oils", "Sugar and sweeteners", "Meat",
                "Milk and eggs", "Fish and seafood", "Fruit and vegetables", "Everything else"]


def build_plate(fao):
    kcal = lambda code: fao_series(fao, code, 664)
    total = kcal("S2901")                                           # FAO "Grand Total"
    parts = {
        "Rice": kcal("S2807"),
        "Wheat and other cereals": kcal("S2905") - kcal("S2807"),   # all cereals minus rice
        "Vegetable oils": kcal("S2914"),
        "Sugar and sweeteners": kcal("S2909"),
        "Meat": kcal("S2943") + kcal("S2945"),                      # meat + offals
        "Milk and eggs": kcal("S2948") + kcal("S2949"),
        "Fish and seafood": kcal("S2960"),
        "Fruit and vegetables": kcal("S2919") + kcal("S2918"),
    }
    parts["Everything else"] = total - sum(parts.values())          # starchy roots, pulses, nuts, spices, drinks ...
    cells, summary = [], []
    dots = {}
    for year in (2010, 2023):
        share = {g: 100 * parts[g][year] / total[year] for g in PLATE_GROUPS}
        dots[year] = layouts.largest_remainder(share)
        cx, cy = PLATE_CENTRES[year]
        order = []
        for g in PLATE_GROUPS:
            order += [g] * dots[year][g]
        for i, c in enumerate(layouts.plate_cells(cx, cy)):
            g = order[i]
            cells.append({"year": year, "cell": i + 1, "x": round(c["x"], 2), "y": round(c["y"], 2), "group": g,
                          "group_order": PLATE_GROUPS.index(g) + 1,
                          "share_pct": share[g], "kcal_per_day": parts[g][year]})
    for k, g in enumerate(PLATE_GROUPS):
        summary.append({"group": g, "group_order": k + 1,
                        "kcal_2010": parts[g][2010], "kcal_2023": parts[g][2023],
                        "share_2010": 100 * parts[g][2010] / total[2010], "share_2023": 100 * parts[g][2023] / total[2023],
                        "dots_2010": dots[2010][g], "dots_2023": dots[2023][g], "row_y": PLATE_FIRST_ROW_Y + 34 * k})
    rims = [{"year": y, "x": c[0], "y": c[1], "rim_size_px2": math.pi * PLATE_RIM_R ** 2, "label_y": 26}
            for y, c in PLATE_CENTRES.items()]
    write(pd.DataFrame(cells), "food_plate_cells.csv")
    write(pd.DataFrame(summary), "food_plate_summary.csv")
    write(pd.DataFrame(rims), "food_plate_rims.csv")


FOODS = [("S2807", "Rice"), ("S2511", "Wheat and flour"), ("S2542", "Sugar"), ("S2914", "Vegetable oils"),
         ("S2734", "Poultry"), ("S2744", "Eggs"), ("S2848", "Milk"), ("S2919", "Fruit"),
         ("S2918", "Vegetables"), ("S2960", "Fish and seafood"), ("S2733", "Pork"), ("S2731", "Beef")]


def build_food_change(fao):
    rows = []
    for code, label in FOODS:
        s = fao_series(fao, code, 645)
        a, b = s.loc[2010:2012].mean(), s.loc[2021:2023].mean()      # three-year averages smooth out yearly noise
        pct = 100 * (b / a - 1)
        rows.append({"food": label, "fao_item_code": code, "kg_2010_12": a, "kg_2021_23": b, "change_kg": b - a,
                     "change_pct": pct,
                     "direction": "more" if pct >= 5 else ("less" if pct <= -5 else "little change")})   # +/-5% = "little change"
    df = pd.DataFrame(rows).sort_values("change_pct", ascending=False).reset_index(drop=True)
    df["sort_order"] = df.index + 1
    write(df, "food_change.csv")


HEAT_GROUPS = [("S2905", "Cereals"), ("S2914", "Vegetable oils"), ("S2909", "Sugar and sweeteners"), ("S2943", "Meat"),
               ("S2948", "Milk"), ("S2960", "Fish and seafood"), ("S2949", "Eggs"), ("S2919", "Fruit"),
               ("S2918", "Vegetables"), ("S2907", "Starchy roots"), ("S2946", "Animal fats"), ("S2923", "Spices")]


def build_heatmap(fao):
    rows = []
    for code, label in HEAT_GROUPS:
        s = fao_series(fao, code, 664)
        for year, v in s.items():
            rows.append({"food_group": label, "year": year, "kcal_per_day": v,
                         "change_pct_vs_2010": 100 * (v / s[2010] - 1),
                         "change_pct_vs_previous_year": (100 * (v / s[year - 1] - 1)) if year > 2010 else np.nan})
    df = pd.DataFrame(rows)
    last = df[df.year == 2023].sort_values("change_pct_vs_2010", ascending=False)
    order = {g: i + 1 for i, g in enumerate(last["food_group"])}
    df["group_order"] = df["food_group"].map(order)                 # sorted by change by 2023, biggest rise first
    write(df, "food_heatmap.csv")


# =====================================================================================================
# 2. DOSM CROP CHARTS (C4 to C11) and the combined chart (C7)
# =====================================================================================================
def load_crops():
    c = pd.read_csv(CROPS_RAW)
    c["year"] = pd.to_datetime(c["date"]).dt.year
    return c


def build_crop_tables(crops, fao, states):
    info = {s["state"]: s for s in states}
    cen = {n: geo.centroid_of_largest_part(s) for n, s in info.items()}
    st = crops[crops.state != "Malaysia"]
    nat = crops[crops.state == "Malaysia"]

    # --- check: the states add up to the national row (they should, to rounding) ---
    tot = st.groupby(["year", "crop_type"])[["planted_area", "production"]].sum()
    ref = nat.set_index(["year", "crop_type"])[["planted_area", "production"]]
    worst = ((tot - ref).abs() / ref.replace(0, np.nan)).max().max()
    print(f"  check: state sums vs Malaysia row, worst relative gap = {100 * worst:.3f}%")

    # --- paddy by state, 2024 (C4 symbol map, C8 choropleth) ---
    p = st[(st.crop_type == "paddy") & (st.year == 2024)].copy()
    p["code_state"] = p["state"].map(lambda n: info[n]["code_state"])
    p["region"] = p["state"].map(lambda n: info[n]["region"])
    p["lon"] = p["state"].map(lambda n: cen[n][0])
    p["lat"] = p["state"].map(lambda n: cen[n][1])
    p["yield_t_ha"] = np.where(p.planted_area > 0, p.production / p.planted_area, np.nan)
    p["share_of_malaysia_pct"] = 100 * p.production / p.production.sum()
    p = p.rename(columns={"planted_area": "planted_area_ha", "production": "production_t"})
    # tile grid map (C4): each state is one equal square; the circle's AREA is proportional to tonnes and the
    # biggest harvest gets the biggest circle that fits inside its square, so no circle can spill outside its state.
    p["display_name"] = p.state.map(lambda n: SHORT_NAMES.get(n, n))
    p["tile_col"] = p.state.map(lambda n: TILES[n][0])
    p["tile_row"] = p.state.map(lambda n: TILES[n][1])
    p["tile_x0"] = TILE_LEFT + p.tile_col * (TILE_SIZE + TILE_GAP)
    p["tile_y0"] = TILE_TOP + p.tile_row * (TILE_SIZE + TILE_GAP)
    p["tile_x1"] = p.tile_x0 + TILE_SIZE
    p["tile_y1"] = p.tile_y0 + TILE_SIZE
    room = (TILE_SIZE - TILE_NAME_SPACE) / 2 - 2                     # largest radius that fits below the name, 2 px margin
    tile_k = room / math.sqrt(p.production_t.max())                  # pixels of radius per square root of a tonne
    p["circle_x"] = (p.tile_x0 + p.tile_x1) / 2
    p["circle_y"] = p.tile_y0 + TILE_NAME_SPACE + (TILE_SIZE - TILE_NAME_SPACE) / 2
    p["circle_radius_px"] = tile_k * np.sqrt(p.production_t)
    assert (p.circle_radius_px <= room + 1e-9).all(), "a circle does not fit inside its square"
    print(f"  C4 tiles: largest circle radius {p.circle_radius_px.max():.1f} px fits a {room:.1f} px space")
    write(p[["state", "display_name", "code_state", "region", "lon", "lat", "planted_area_ha", "production_t", "yield_t_ha",
             "share_of_malaysia_pct", "tile_col", "tile_row", "tile_x0", "tile_y0", "tile_x1", "tile_y1",
             "circle_x", "circle_y", "circle_radius_px"]]
          .round({"lon": 5, "lat": 5, "circle_radius_px": 2}), "paddy_by_state_2024.csv")
    # the size legend in the C4 spec must use the same pixels per tonne as the circles
    print(f"  C4 size legend: for a scale domain of [0, 800000] use a size range of [0, {math.pi * tile_k ** 2 * 800000:.1f}] px^2")

    # --- dot map (C5): 1 dot = 5,000 tonnes, placed at random inside each state ---
    rng = np.random.RandomState(3179)
    crop_names = {"vegetables": "Vegetables", "fruits": "Fruit", "coconut": "Coconut"}
    dots, top = [], []
    s24 = st[st.year == 2024]
    for name, s in info.items():
        placed = []
        for crop in ("vegetables", "fruits", "coconut"):
            row = s24[(s24.state == name) & (s24.crop_type == crop)]
            n = int(round(row.production.iloc[0] / 5000)) if len(row) else 0
            for lon, lat in geo.sample_points_inside(s, n, rng, existing=placed):
                dots.append({"crop": crop_names[crop], "state": name, "region": s["region"], "lon": lon, "lat": lat})
                placed.append((lon, lat))
    d = pd.DataFrame(dots)
    d.insert(0, "dot_id", range(1, len(d) + 1))
    write(d.round({"lon": 5, "lat": 5}), "crop_dots.csv")
    for crop, label in crop_names.items():
        r = s24[s24.crop_type == crop].sort_values("production", ascending=False)
        t = r.iloc[0]
        top.append({"crop": label, "state": t.state, "region": info[t.state]["region"], "production_t": t.production,
                    "share_pct": 100 * t.production / r.production.sum(), "lon": cen[t.state][0], "lat": cen[t.state][1]})
    write(pd.DataFrame(top).round({"lon": 5, "lat": 5}), "crop_top_states_2024.csv")

    # --- lollipop chart (C6): harvest by crop group, Malaysia 2024 ---
    n24 = nat[(nat.year == 2024) & (nat.crop_type != "flower")].copy()    # "flower" is counted in stems, not tonnes
    names = {"paddy": "Paddy", "fruits": "Fruit", "industrial_crops": "Industrial crops", "coconut": "Coconut",
             "vegetables": "Vegetables", "cash_crops": "Cash crops", "spices": "Spices", "herbs": "Herbs"}
    n24["label"] = n24.crop_type.map(names)
    n24 = n24.sort_values("production", ascending=False).reset_index(drop=True)
    write(n24[["crop_type", "label"]].assign(production_t=n24.production), "crop_harvest.csv")

    # --- national paddy by year (C9) ---
    pn = nat[nat.crop_type == "paddy"].set_index("year").sort_index()
    out = pd.DataFrame({"year": pn.index, "planted_area_ha": pn.planted_area.values, "production_t": pn.production.values})
    out["yield_t_ha"] = out.production_t / out.planted_area_ha
    base = out.iloc[0]
    out["area_change_pct_vs_2014"] = 100 * (out.planted_area_ha / base.planted_area_ha - 1)
    out["yield_change_pct_vs_2014"] = 100 * (out.yield_t_ha / base.yield_t_ha - 1)
    out["harvest_change_pct_vs_2014"] = 100 * (out.production_t / base.production_t - 1)
    write(out, "paddy_national.csv")

    # --- the combined chart (C7): DOSM paddy tonnes divided by FAO population, next to FAO rice per person ---
    pop = fao_series(fao, "S2501", 511) * 1000              # FAO population is in thousands
    rice = fao_series(fao, "S2807", 645)
    rows = []
    for year in range(2014, 2024):
        rows.append({"year": year, "series_id": "paddy", "series": "Paddy harvested per person",
                     "kg_per_person": pn.production[year] * 1000 / pop[year], "population": pop[year]})
        rows.append({"year": year, "series_id": "rice", "series": "Rice available per person",
                     "kg_per_person": rice[year], "population": pop[year]})
    df = pd.DataFrame(rows)
    df["index_2014"] = df.groupby("series_id")["kg_per_person"].transform(lambda s: 100 * s / s.iloc[0])
    write(df, "paddy_vs_rice_per_person.csv")

    # --- Dorling cartogram (C10): change in paddy harvest by state, 2014 to 2024 ---
    a = st[(st.crop_type == "paddy") & (st.year == 2014)].set_index("state")["production"]
    z = st[(st.crop_type == "paddy") & (st.year == 2024)].set_index("state")["production"]
    d = pd.DataFrame({"production_2014_t": a, "production_2024_t": z})
    d = d[(d.production_2014_t > 0) | (d.production_2024_t > 0)].copy()
    d["change_t"] = d.production_2024_t - d.production_2014_t
    d["change_pct"] = 100 * d.change_t / d.production_2014_t
    d["direction"] = np.where(d.change_t < 0, "lost", "gained")
    net = d.change_t.sum()
    d["share_of_net_change_pct"] = 100 * d.change_t / net
    d = d.reset_index().rename(columns={"index": "state"})
    homes_proj = [geo.albers(*cen[s]) for s in d.state]
    # starting positions: the same projection and scale as the maps (3300 px per unit, about 58 px per degree).
    # East Malaysia is pulled closer to the Peninsula (x only) so the circles fit the canvas.
    reg = [info[st]["region"] for st in d.state]
    pen_x = [p[0] for p, r in zip(homes_proj, reg) if r == "peninsula"]
    east_x = [p[0] for p, r in zip(homes_proj, reg) if r != "peninsula"]
    mid_y = (max(p[1] for p in homes_proj) + min(p[1] for p in homes_proj)) / 2
    homes = []
    for (hx, hy), r in zip(homes_proj, reg):
        x = 230 + (hx - min(pen_x)) * 3300 if r == "peninsula" else 640 + (hx - min(east_x)) * 3300 * 1.0
        homes.append((x, DORLING_AREA_H / 2 - (hy - mid_y) * 3300))
    kk = DORLING_MAX_R / math.sqrt(d.change_t.abs().max())   # the biggest circle has a DORLING_MAX_R px radius
    radii = [kk * math.sqrt(abs(v)) for v in d.change_t]
    pos = layouts.dorling(homes, radii, DORLING_W, DORLING_AREA_H)
    d["x"] = [p[0] for p in pos]
    d["y"] = [p[1] for p in pos]
    d["radius_px"] = radii
    d["size_px2"] = [math.pi * r * r for r in radii]
    d["label_inside"] = 0      # every label sits just outside its circle, so all labels look the same
    label_text = [max(name, f"{v:+,.0f} tonnes", key=len) for name, v in zip(d.state, d.change_t)]   # the wider of the two label lines
    lx, ly, al = layouts.place_labels(list(d.x), list(d.y), radii, list(d.label_inside), label_text, DORLING_W, DORLING_AREA_H)
    d["label_x"], d["label_y"], d["label_align"] = lx, ly, al
    ends = layouts.leader_ends(list(d.x), list(d.y), radii, lx, ly, al)
    d["edge_x"], d["edge_y"], d["lead_x"], d["lead_y"] = [e[0] for e in ends], [e[1] for e in ends], [e[2] for e in ends], [e[3] for e in ends]
    write(d.round(2).assign(change_pct=d.change_pct, share_of_net_change_pct=d.share_of_net_change_pct), "paddy_change_by_state.csv")

    # --- treemap (C11): planted land, Malaysia 2024, in two levels: crop group (parent) and state (child) ---
    tn = {"paddy": "Paddy", "fruits": "Fruit", "industrial_crops": "Industrial crops", "coconut": "Coconut",
          "vegetables": "Vegetables", "cash_crops": "Cash crops", "spices": "Spices", "flower": "Flowers", "herbs": "Herbs"}
    leaf = st[(st.year == 2024) & (st.planted_area > 0)][["crop_type", "state", "planted_area"]].copy()
    groups = leaf.groupby("crop_type").planted_area.sum().sort_values(ascending=False)       # parent size = sum of its states
    prod = nat[nat.year == 2024].set_index("crop_type").production                         # national harvest, for the labels
    parents = layouts.squarify(list(groups.values), 0, 0, TREEMAP_W, TREEMAP_H)
    total_land = groups.sum()
    PAD = 1.5                                                                              # parent border, so groups read as blocks
    rows = []
    for (crop, area), (x0, y0, x1, y1) in zip(groups.items(), parents):
        kids = leaf[leaf.crop_type == crop].sort_values("planted_area", ascending=False)
        rects = layouts.squarify(list(kids.planted_area), x0 + PAD, y0 + PAD, (x1 - x0) - 2 * PAD, (y1 - y0) - 2 * PAD)
        for (_, kr), (a0, b0, a1, b1) in zip(kids.iterrows(), rects):
            rows.append({"crop_type": crop, "label": tn[crop], "state": kr.state, "display_name": SHORT_NAMES.get(kr.state, kr.state),
                         "planted_area_ha": kr.planted_area, "share_of_group_pct": 100 * kr.planted_area / area,
                         "group_area_ha": area, "group_share_pct": 100 * area / total_land,
                         "group_production_t": (np.nan if crop == "flower" else prod[crop]),   # flower is not measured in tonnes
                         "x0": a0, "y0": b0, "x1": a1, "y1": b1, "gx0": x0, "gy0": y0, "gx1": x1, "gy1": y1})
    t = pd.DataFrame(rows)
    gw, gh = t.gx1 - t.gx0, t.gy1 - t.gy0
    t["group_label_lines"] = np.where((gw >= 190) & (gh >= 110), 3, np.where((gw >= 70) & (gh >= 34), 2, 0))   # 3 = name, share, harvest
    w, h = t.x1 - t.x0, t.y1 - t.y0
    t["state_label"] = ((w >= 64) & (h >= 22) & (t.crop_type == "paddy")).astype(int)       # name the big paddy states only
    write(t.round({c: 2 for c in ["x0", "y0", "x1", "y1", "gx0", "gy0", "gx1", "gy1"]}), "landuse_treemap.csv")
    nat_share = 100 * nat[(nat.year == 2024) & (nat.crop_type == "paddy")].planted_area.iloc[0] / nat[nat.year == 2024].planted_area.sum()
    print(f"  C11 check: paddy share of planted land, sum of states {100 * groups['paddy'] / total_land:.2f}%, Malaysia row {nat_share:.2f}%")

    # --- where each map annotation sits (layout only; the TEXT of every annotation is built from the data in the spec) ---
    ann = [("C5", "Pahang", 103.56, 5.18), ("C5", "Johor", 103.81, 1.12),
           ("C8", "Pulau Pinang", 101.4, 7.05), ("C8", "Sarawak", 111.3, 4.6)]
    write(pd.DataFrame([{"chart": c, "state": s, "region": info[s]["region"], "anchor_lon": lo, "anchor_lat": la}
                        for c, s, lo, la in ann]), "map_annotations.csv")


# =====================================================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fao-full", help="path to the full FAO CSV; only needed to (re)create data/raw/FoodBalanceSheets_E_Malaysia.csv")
    args = ap.parse_args()
    CLEAN.mkdir(parents=True, exist_ok=True)
    if args.fao_full:
        make_fao_extract(args.fao_full)
    if not FAO_EXTRACT.exists():
        raise SystemExit("data/raw/FoodBalanceSheets_E_Malaysia.csv is missing. Run once with --fao-full <path to the FAO CSV>.")
    fao = load_fao()
    states = geo.decode_topology(json.load(open(TOPO)))
    print("FAO charts"); build_plate(fao); build_food_change(fao); build_heatmap(fao)
    print("DOSM charts"); build_crop_tables(load_crops(), fao, states)
    print("Done.")


if __name__ == "__main__":
    main()
