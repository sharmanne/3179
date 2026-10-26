# Less rice, more milk

FIT3179 Data Visualisation 2, Monash University Malaysia, Semester 2 2026. Topic: Cooking and Baking.

A single scrolling page with 11 Vega-Lite charts about how Malaysians' food has changed since 2010 (FAO food balances) and what is happening to the paddy fields that grow our rice (DOSM crops by state).

Live page: https://sharmanne.github.io/3179/

## Files

```
index.html            the page: hero, six story sections, footer
css/style.css         design tokens, 12-column grid, all styling (plain CSS)
js/main.js            loads each chart's spec from specs/ with vega-embed
specs/                one Vega-Lite JSON file per chart (c01 to c11)
data/raw/             the source files exactly as published (FAO extract for Malaysia, DOSM crops, DOSM boundaries)
data/clean/           files the charts read, built from data/raw
scripts/              prepare_data.py (cleaning, joins), geo.py, layouts.py, check_claims.py, make_boundaries.txt
DATA_SOURCES.md       sources, licences, every cleaning step, spot checks
```

## Run it on your computer

Use a local web server, not a double-click on `index.html`: browsers block a page opened as a file (`file://`) from reading the spec and data files.

- **VS Code:** install the Live Server extension, right-click `index.html`, choose "Open with Live Server".
- **Terminal:** in this folder run `python -m http.server 8766`, then open <http://127.0.0.1:8766/>.

To rebuild the cleaned data: `python scripts/prepare_data.py` (needs pandas and numpy). To re-check every number quoted on the page against the raw data: `python scripts/check_claims.py`.

## Libraries (pinned)

Vega 5.22.1, Vega-Lite 5.2.0 and vega-embed 6.20.8, loaded from jsDelivr. Fonts: Fraunces and Source Sans 3 from Google Fonts.

## Before submission

Check the wording of the AI acknowledgement in the footer of `index.html`, and upload the hand-drawn sketch as a PDF to this repository (the Moodle form asks for its URL).
