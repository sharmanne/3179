# Data sources, cleaning steps and checks

FIT3179 Data Visualisation 2, Monash University Malaysia, Semester 2 2026. Topic: Cooking and Baking.

Two independent sources are combined: **FAOSTAT Food Balances** (what food is available per person) and **DOSM Crop Area and Production by State** (what Malaysia grows). A third file, the DOSM state boundaries, is used only to draw the maps.

## 1. Sources

| # | Publisher / author | Title | URL | Date accessed | Licence | How it is used |
|---|---|---|---|---|---|---|
| 1 | Food and Agriculture Organization of the United Nations (FAO), FAOSTAT | Food Balances (2010-), "Food Balance Sheets", Malaysia, 2010 to 2023 | Dataset page: https://www.fao.org/faostat/en/#data/FBS<br>Bulk file: https://bulks-faostat.fao.org/production/FoodBalanceSheets_E_All_Data_(Normalized).zip | **[YOU: write the date you downloaded it]** | CC BY 4.0 plus FAO database terms of use: https://www.fao.org/contact-us/terms/db-terms-of-use/en/ | C1 plate, C2 dumbbell, C3 heatmap, and the rice and population series in C7 |
| 2 | Department of Statistics Malaysia (DOSM), with the Department of Agriculture, published on the DOSM open data portal | Crop Area and Production by State (`crops_state`), 2014 to 2024 | Dataset page: https://open.dosm.gov.my/data-catalogue/crops_state<br>CSV: https://storage.data.gov.my/agriculture/crops_state.csv | **[YOU: write the date you downloaded it]** | CC BY 4.0 | C4 to C11 and the paddy series in C7 |
| 3 | DOSM open data repository | State boundaries, `administrative_1_state.geojson` | https://github.com/dosm-malaysia/data-open/tree/main/datasets/geodata | **[YOU: write the date you downloaded it]** | DOSM Open Data Licence | Map shapes for C4, C5, C8 only. Contains no values. |

Please check each licence on its own page before you submit. This table repeats what the dataset pages said when I read them; it is not legal advice.

The only link between sources 1 and 2 is **year** (C7 divides DOSM paddy tonnes by the FAO population of the same year). Source 3 joins to source 2 by state name; the names are identical in both files, so nothing had to be renamed.

## 2. Files and what was done to them

```
data/raw/    the files exactly as published (nothing edited by hand)
data/clean/  everything the charts read; built from data/raw by scripts/prepare_data.py
```

| File in data/raw | Size | Note |
|---|---|---|
| `crops_state.csv` | 68,546 bytes | Untouched copy of the DOSM CSV. |
| `administrative_1_state.geojson` | 391,521 bytes | Untouched copy of the DOSM boundaries. |
| `FoodBalanceSheets_E_Malaysia.csv` | 3,022,428 bytes | The FAO "all data" file is 633 MB, so only the rows with Area Code 131 (Malaysia) are kept here. Rows and values are copied as they are; the only change is that every field is wrapped in quotes. SHA-256 of the full FAO file: `2834e1012daaebf4e4f8195fa86ce9063d1c81fdd9d7c04cbf0aba758ccfa020`. |

### Every change the script makes

1. **Filter rows.** FAO: Malaysia only (the extract above). DOSM: separates the national row ("Malaysia") from the state rows.
2. **Fix names and codes.** None needed. FAO item codes carry a leading apostrophe (`'S2807`); it is removed to make a plain code.
3. **Parse dates.** DOSM `date` (for example `2024-01-01`) becomes the integer `year`.
4. **Join.** DOSM paddy by year is joined to FAO population by year (C7). DOSM state names are joined to boundary names (maps).
5. **Pre-aggregate.** Three-year averages (C2), shares of the day's food energy (C1), changes against 2010 (C3), state shares of Malaysia (C4, C5), yield (C8), changes 2014 to 2024 (C9, C10), shares of planted land (C11). Every formula is below.
6. **Layout only.** The three charts that are drawn from screen positions (C1 plate, C10 Dorling cartogram, C11 treemap) and the C5 dots have their pixel positions worked out in the script, because Vega-Lite has no relaxation or treemap layout. These columns (`x`, `y`, `x0`…`y1`, `radius_px`, `size_px2`, `label_*`, `lon`/`lat` of dots) are positions, not data. The value shown by each shape is still the data value.
7. **Format.** Numbers are written with 4 decimals. No source value is rounded, replaced or adjusted. The one exception to "exact": the C1 plate needs whole dots that add up to 100, so shares are turned into dots by the largest-remainder rule (a row can differ from its true share by under 1 point; both numbers are kept in `food_plate_summary.csv`).
8. **Boundary simplification.** mapshaper, Visvalingam, 10% of points kept, `keep-shapes`, split into two objects (`peninsula`, `east`). 391,521 bytes become 23,754 bytes. Recipe: `scripts/make_boundaries.txt`.

### Derived values and their formulas

| Quantity | Formula | Used in |
|---|---|---|
| Share of food energy | FAO element 664 (kcal per person per day): group ÷ Grand Total (S2901) × 100. "Wheat and other cereals" = all cereals (S2905) − rice (S2807). "Meat" = S2943 + S2945. "Milk and eggs" = S2948 + S2949. "Fruit and vegetables" = S2919 + S2918. "Everything else" = total − the groups above. | C1 |
| Change in food per person | Mean of 2021–23 ÷ mean of 2010–12 − 1, from FAO element 645 (kg per person per year). "Little change" means within ±5%. | C2 |
| Change vs 2010 and vs previous year | kcal per day in year ÷ kcal in 2010 (or in the previous year) − 1 | C3 |
| Share of Malaysia's harvest | State production ÷ Malaysia production × 100, same crop and year (DOSM national row). | C4, C5 |
| Dots | One dot = 5,000 tonnes: round(state production ÷ 5,000). Dots are placed at random inside the state (fixed seed 3179). | C5 |
| Yield | Production (tonnes) ÷ planted area (hectares) | C8, C9 |
| Paddy per person | DOSM national paddy production × 1,000 ÷ (FAO population in thousands × 1,000), kg | C7 |
| Index (2014 = 100) | Value ÷ value in 2014 × 100 | C7 |
| Change in harvest | Production 2024 − production 2014, by state | C10 |
| Share of net change | State change ÷ sum of all states' changes × 100 (the sum includes the two states that gained) | C10 |
| Share of planted land | Planted area ÷ sum of the nine crop groups' planted areas × 100 | C11 |

Checks built into the script: the state rows add up to the national row (to rounding), and every FAO series has exactly 14 years.

### Files in data/clean

| File | Rows | Bytes | Columns |
|---|---|---|---|
| `crop_harvest.csv` | 8 | 270 | crop_type, label, production_t |
| `crop_dots.csv` | 792 | 35,405 | dot_id, crop, state, region, lon, lat |
| `crop_top_states_2024.csv` | 3 | 234 | crop, state, region, production_t, share_pct, lon, lat |
| `food_change.csv` | 12 | 750 | food, fao_item_code, kg_2010_12, kg_2021_23, change_kg, change_pct, direction, sort_order |
| `food_heatmap.csv` | 168 | 6,984 | food_group, year, kcal_per_day, change_pct_vs_2010, change_pct_vs_previous_year, group_order |
| `food_plate_cells.csv` | 200 | 11,723 | year, cell, x, y, group, group_order, share_pct, kcal_per_day |
| `food_plate_rims.csv` | 2 | 84 | year, x, y, rim_size_px2, label_y |
| `food_plate_summary.csv` | 9 | 619 | group, group_order, kcal_2010, kcal_2023, share_2010, share_2023, dots_2010, dots_2023, row_y |
| `landuse_treemap.csv` | 9 | 868 | crop_type, label, planted_area_ha, production_t, share_pct, x0, y0, x1, y1, label_inside, label_lines |
| `map_annotations.csv` | 5 | 220 | chart, state, region, anchor_lon, anchor_lat (where a note sits; its text is built from the data inside the spec) |
| `paddy_by_state_2024.csv` | 15 | 1,649 | state, code_state, region, lon, lat, planted_area_ha, production_t, yield_t_ha, share_of_malaysia_pct, symbol_radius_px, label_side, label_lon, label_lat |
| `paddy_change_by_state.csv` | 13 | 1,789 | state, production_2014_t, production_2024_t, change_t, change_pct, direction, share_of_net_change_pct, x, y, radius_px, size_px2, label_inside, label_x, label_y, label_align |
| `paddy_national.csv` | 11 | 799 | year, planted_area_ha, production_t, yield_t_ha, area_change_pct_vs_2014, yield_change_pct_vs_2014, harvest_change_pct_vs_2014 |
| `paddy_vs_rice_per_person.csv` | 20 | 1,410 | year, series_id, series, kg_per_person, population, index_2014 |
| `states.topojson` | 2 objects | 23,754 | state, code_state, region (boundaries only) |

Page weight: `index.html` 27 KB, `css/style.css` 13 KB, `js/main.js` 8 KB, `specs/` 91 KB, `data/clean/` 87 KB; about 0.23 MB of our own files. The libraries (Vega, Vega-Lite, vega-embed) and the two typefaces come from CDNs. `data/raw/` (3.5 MB) is in the repository for the audit trail but the page never loads it.

## 3. Spot checks: original file next to the cleaned file

| What | Original (data/raw) | Cleaned (data/clean) |
|---|---|---|
| Kedah, paddy, 2024, production | `crops_state.csv`: Kedah, 2024-01-01, paddy, production **777021.0** | `paddy_by_state_2024.csv`: production_t **777021.0** |
| Kedah, paddy, 2024, planted area | planted_area **213556.0** | planted_area_ha **213556.0**; yield_t_ha 3.6385 (= 777021 ÷ 213556) |
| Pulau Pinang, paddy, 2024 | production 116402.0, planted_area 24210.0 | production_t 116402.0; yield_t_ha 4.8080 |
| Sarawak, paddy, 2014 and 2024 | production 232078.0 and 84510.0 | `paddy_change_by_state.csv`: production_2014_t 232078.0, production_2024_t 84510.0, change_t −147568.0 |
| Malaysia, paddy, 2014 | planted_area 679239.0, production 2844983.0 | `paddy_national.csv`: planted_area_ha 679239.0, production_t 2844983.0, yield 4.1885 |
| Malaysia, fruit, 2024 | production 1968956.6 | `crop_harvest.csv`: production_t 1968956.6 |
| FAO rice, kcal per person per day, 2010 and 2023 | `FoodBalanceSheets_E_Malaysia.csv`: S2807, element 664, 2010 **838.67**, 2023 **700.52** | `food_plate_summary.csv` (Rice): kcal_2010 **838.67**, kcal_2023 **700.52**; share 29.5984% and 23.937%; dots 30 and 24 |
| FAO milk, kg per person per year | 2010 22.57, 2011 21.44, 2012 26.76; 2021 39.87, 2022 39.14, 2023 44.80 | `food_change.csv` (Milk): kg_2010_12 **23.59** (= mean of the first three), kg_2021_23 **41.27**, change_pct 74.947 |

Run `python scripts/check_claims.py` to recompute all 42 numbers quoted on the page (titles, notes, headline text) from `data/raw`. Last run: 42 checked, 0 wrong.

## 4. Things a careful reader should know

- Every FAO value in this file carries a flag: 13,491 rows are `I` (imputed by FAO), 9,902 are `E` (estimated) and 14 are `X` (figures from other organisations, the population rows). The FAO figures are modelled estimates of **food available**, not food eaten. Food available per person is the national supply divided by the population, so it is higher than what a person actually eats.
- The C7 chart divides DOSM paddy (unmilled rice, tonnes) by the FAO population. Paddy is not rice: milling removes the husk and bran, so rice weighs less than the paddy it comes from, and part of the rice available is imported. The chart compares **trends** (both indexed to 2014), not kilograms of rice.
- DOSM "planted area" counts the area in the crop group for that year. DOSM flower production is not in tonnes, so flowers are left out of C6.
- Maps: Peninsular and East Malaysia are drawn side by side at the same scale (conic equal-area projection, parallels 2° and 6° N, central meridian 109.6° E). The gap between them is not to scale.
- C5 dots are random positions inside each state. They show how much, not where the farms are.
- C10 circles are placed by a relaxation algorithm; they sit near their states but are not in their exact positions.
