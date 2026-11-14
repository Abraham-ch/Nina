# NINA: global scope of the MVP

## Period decision

The global MVP uses **2025–2026**, limited to the dates actually loaded. The team's files start on **5 November 2025**; the recent edge is extended with the seven-day MODIS CSV and the windows already downloaded through the API.

The initial selection is **July 2026 and VIIRS NOAA-20**, a month included in the standard files of MODIS, S-NPP, NOAA-20 and NOAA-21. Month, country, instrument or drawn area can be changed.

This period was chosen because it uses the global set already available, covers roughly one cycle of the seasons and allows several instruments to be tested without downloading whole decades. The global originals take up tens of GB; block processing and analytical storage avoid loading them into memory together.

**This scope demonstrates global exploration. Building global historical references requires more years.** No anomaly is computed against five years where only about one exists. Historical extension should prioritize the areas of interest and reuse aggregates, rather than immediately downloading every global original since 2000.

The Peruvian 2000–2025 history is kept as a regional set. It is not presented as global history.

## Inputs used

The originals stay in `source/` (on the original machine, `data_abraham/`), outside Git:

| File or group | Content |
|---|---|
| `fire_archive_M-C61_844123.json` | MODIS Terra/Aqua standard |
| `fire_archive_SV-C2_844126.json` | VIIRS S-NPP standard |
| `fire_archive_J1V-C2_844124.json` | VIIRS NOAA-20 standard |
| `fire_archive_J2V-C2_844125.json` | VIIRS NOAA-21 standard |
| Four `fire_nrt_` files for those instruments | Later provisional records |
| `MODIS_C6_1_Global_7d.csv` | Recent MODIS update |
| `fire_nrt_LS_844122.json` | Landsat: excluded from the MODIS/VIIRS scope and recorded as an excluded file |

Naming, standard/NRT separation, WGS84 coordinates and data use were checked against the [official FIRMS Readme](https://firms.modaps.eosdis.nasa.gov/download/Readme.txt). For current availability the FIRMS catalog is also used: the Readme contains a note about the absence of standard NOAA-20/21 products that does not match the delivered files or the catalog consulted; that note is not used as a fixed rule in the program.

## Processing applied

1. Read CSV and JSON with bounded memory; keep the originals.
2. Identify instrument and platform, normalize UTC date/time and coordinates.
3. Check dates, coordinates, confidence and numeric fields. Record the reason for each exclusion and fail if more than 1 % are invalid.
4. Identify technical duplicates and apply standard-over-NRT precedence within their scope. This avoids counting revisions of one observation as new detections.
5. Load detections from the whole world. Assignment to Peruvian divisions is only an extra attribute; points from other territories are kept.
6. Query by source, territory and month. For countries, the exact reference geometry is filtered after the rectangular filter.
7. Show complete counts and a limited sample of points on the map. Export all selected observations in blocks.

Ingestion keeps detections of different types and confidence levels; it does not claim that every point is a wildfire. The vegetation filter depends on the product including that attribute.

## Integrity and meaning of the dates

The minimum and maximum dates of a detection file **do not prove that every day and place was observed**. That is why these batches have the availability basis `observed_dates_only`. The calendar shows existing counts and keeps the partial or unknown-integrity state. It does not invent zeros for empty areas or sky-coverage percentages.

The global map, the calendar and the exports use observed data. The calibration experiment remains Peruvian; it is not applied automatically to every country. Scientific harmonization and its global validation remain pending.

## Reproducible run

From the root, with the server kept separate from the staging database:

```powershell
.\.venv\Scripts\python.exe -u scripts/import_global.py --input source --data-dir data/world-build --start-year 2025 --end-year 2026
.\.venv\Scripts\python.exe -u scripts/verify_world.py --data-dir data/world-build --refresh-parquet
```

The first command keeps already completed batches and resumes per file. Do not run another import on the same database or activate that database in the server while it is being written from the console.

The verification checks the hashes and row balance of the nine global files, looks for duplicate identities and cross-checks July 2026 queries in Brazil, Australia, Indonesia, the United States and the Democratic Republic of the Congo. It also checks that map counts match the analysis and that Parquet keeps every row.

Quantitative results are saved locally in `data/global-import.json` and `data/release-world-v0.3.json` when the database is activated. Generated data and reports stay outside Git; the code and these instructions are versioned.
