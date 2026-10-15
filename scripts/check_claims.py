#!/usr/bin/env python3
"""check_claims.py: recomputes every number quoted on the page from the ORIGINAL files in data/raw
(not from data/clean) and compares it with the number written on the page or in a chart.

Run from the site folder:   python scripts/check_claims.py
It prints one line per claim: OK or WRONG, the number on the page and the number from the raw data.
It shares no code with prepare_data.py, so it is an independent check of that script.
"""
import sys
from pathlib import Path
import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
CLEAN = Path(__file__).resolve().parent.parent / "data" / "clean"

crops = pd.read_csv(RAW / "crops_state.csv")
crops["year"] = pd.to_datetime(crops["date"]).dt.year
states = crops[crops.state != "Malaysia"]
nat = crops[crops.state == "Malaysia"]

fao = pd.read_csv(RAW / "FoodBalanceSheets_E_Malaysia.csv", dtype=str, keep_default_na=False)
fao["code"] = fao["Item Code (FBS)"].str.lstrip("'")
fao["Year"] = fao["Year"].astype(int)
fao["v"] = pd.to_numeric(fao["Value"])


def f(code, element):                       # one FAO series, indexed by year
    return fao[(fao.code == code) & (fao["Element Code"] == str(element))].set_index("Year")["v"].sort_index()


def crop(df, state, kind, year, col):
    return float(df[(df.state == state) & (df.crop_type == kind) & (df.year == year)][col].iloc[0])


results = []


def check(name, on_page, from_raw, tol):
    ok = abs(on_page - from_raw) <= tol
    results.append(ok)
    print(f"{'OK   ' if ok else 'WRONG'} {name:<62} page {on_page:>10.2f}   raw {from_raw:>12.4f}   (tolerance {tol})")


print("--- FAO claims (C1, C2, C3, hero) ---")
kcal = lambda c: f(c, 664)
total = kcal("S2901")
# Dots are whole numbers that must add up to 100 (largest-remainder rounding), so a row can differ from its true share by under 1 point.
check("C1 rice share of food energy 2010, % (30 dots)", 30, 100 * kcal("S2807")[2010] / total[2010], 1.0)
check("C1 rice share of food energy 2023, % (24 dots)", 24, 100 * kcal("S2807")[2023] / total[2023], 1.0)
check("C1 sugar and sweeteners 2023, % (15 dots)", 15, 100 * kcal("S2909")[2023] / total[2023], 1.0)
check("C1 meat plus offal 2023, % (9 dots)", 9, 100 * (kcal("S2943")[2023] + kcal("S2945")[2023]) / total[2023], 1.0)

for code, label, claimed in [("S2807", "rice", -15), ("S2848", "milk", 75), ("S2744", "eggs", 40), ("S2919", "fruit", 34),
                             ("S2960", "fish and seafood", -11), ("S2511", "wheat and flour", 0), ("S2542", "sugar", -1)]:
    s = f(code, 645)
    pct = 100 * (s.loc[2021:2023].mean() / s.loc[2010:2012].mean() - 1)
    check(f"C2 {label}: change in kg per person, 2010-12 to 2021-23, %", claimed, pct, 0.6)
rice = f("S2807", 645)
check("C2 rice: kg per person a year lost, 2010-12 to 2021-23", 20, rice.loc[2010:2012].mean() - rice.loc[2021:2023].mean(), 0.6)

fruit_kcal, eggs_kcal = kcal("S2919"), kcal("S2949")
check("C3 fruit energy 2021 vs 2020, % (+34)", 34, 100 * (fruit_kcal[2021] / fruit_kcal[2020] - 1), 0.6)
check("C3 eggs energy 2019 vs 2018, % (-23)", -23, 100 * (eggs_kcal[2019] / eggs_kcal[2018] - 1), 0.6)

print("--- DOSM claims (C4 to C6, C8 to C11) ---")
paddy24 = states[(states.crop_type == "paddy") & (states.year == 2024)].set_index("state")
paddy14 = states[(states.crop_type == "paddy") & (states.year == 2014)].set_index("state")
nat_p = nat[nat.crop_type == "paddy"].set_index("year")
tot24 = float(nat_p.loc[2024, "production"])
check("C4 Kedah share of Malaysia's 2024 paddy, %", 38, 100 * paddy24.loc["Kedah", "production"] / tot24, 0.6)
top4 = paddy24.production.sort_values(ascending=False).head(4)
check("S3 four biggest paddy states' share of 2024 harvest, %", 72, 100 * top4.sum() / tot24, 0.6)
for kind, state, claimed, label in [("vegetables", "Pahang", 45, "vegetables"), ("fruits", "Johor", 39, "fruit")]:
    n = float(nat[(nat.crop_type == kind) & (nat.year == 2024)].production.iloc[0])
    check(f"C5 {state} share of Malaysia's 2024 {label}, %", claimed, 100 * crop(states, state, kind, 2024, "production") / n, 0.6)

check("C6 paddy harvest 2024, million t", 2.06, nat_p.loc[2024, "production"] / 1e6, 0.006)
check("C6 fruit harvest 2024, million t", 1.97, float(nat[(nat.crop_type == "fruits") & (nat.year == 2024)].production.iloc[0]) / 1e6, 0.006)

y = (paddy24.production / paddy24.planted_area).dropna()
check("C8 Pulau Pinang yield 2024, t per ha", 4.8, y["Pulau Pinang"], 0.06)
check("C8 Sarawak yield 2024, t per ha", 1.9, y["Sarawak"], 0.06)
check("C8 Pulau Pinang yield divided by Sarawak yield (2.6 times)", 2.6, y["Pulau Pinang"] / y["Sarawak"], 0.06)

a14, a24 = nat_p.loc[2014, "planted_area"], nat_p.loc[2024, "planted_area"]
p14, p24 = nat_p.loc[2014, "production"], nat_p.loc[2024, "production"]
check("C9 paddy fields 2014 to 2024, % change", -15, 100 * (a24 / a14 - 1), 0.6)
check("C9 paddy yield 2014 to 2024, % change", -15, 100 * ((p24 / a24) / (p14 / a14) - 1), 0.6)
check("S5 paddy harvest 2014 to 2024, % change", -28, 100 * (p24 / p14 - 1), 0.6)
check("C9 2014 paddy fields, thousand ha", 679, a14 / 1000, 0.6)
check("C9 2014 yield, t per ha", 4.2, p14 / a14, 0.06)
check("C9 2024 paddy fields, thousand ha", 580, a24 / 1000, 0.6)
check("C9 2024 yield, t per ha", 3.6, p24 / a24, 0.06)

change = (paddy24.production.reindex(paddy14.index.union(paddy24.index)).fillna(0)
          - paddy14.production.reindex(paddy14.index.union(paddy24.index)).fillna(0))
net = change.sum()
check("C10 Kedah plus Sarawak share of net change in paddy harvest, %", 52, 100 * (change["Kedah"] + change["Sarawak"]) / net, 0.6)
check("C10 number of states whose harvest rose (Pahang, Melaka)", 2, int((change > 0).sum()), 0)

land24 = nat[nat.year == 2024].set_index("crop_type").planted_area
check("C11 paddy share of the nine crop groups' planted land, %", 53, 100 * land24["paddy"] / land24.sum(), 0.6)
check("S6 fruit land divided by paddy land (about a third)", 0.33, land24["fruits"] / land24["paddy"], 0.05)

print("--- Combined claims (C7, S4, hero): DOSM paddy tonnes divided by FAO population ---")
pop = f("S2501", 511) * 1000
per_person = lambda yr: nat_p.loc[yr, "production"] * 1000 / pop[yr]
check("C7 paddy per person 2014, kg (93)", 93, per_person(2014), 0.6)
check("C7 paddy per person 2023, kg (62)", 62, per_person(2023), 0.6)
check("C7 paddy per person 2023 vs 2014, % (-33)", -33, 100 * (per_person(2023) / per_person(2014) - 1), 0.6)
check("C7 rice available per person 2014, kg (121)", 121, rice[2014], 0.6)
check("C7 rice available per person 2023, kg (118)", 118, rice[2023], 0.6)
check("C7 rice available per person 2023 vs 2014, % (-3)", -3, 100 * (rice[2023] / rice[2014] - 1), 0.6)
low = (100 * rice.loc[2014:2023] / rice[2014])
check("C7 year of lowest rice index (2017)", 2017, int(low.idxmin()), 0)
check("C7 lowest rice index value (92.6)", 92.6, float(low.min()), 0.06)

print()
bad = results.count(False)
print(f"{len(results)} claims checked, {bad} wrong.")
sys.exit(1 if bad else 0)
