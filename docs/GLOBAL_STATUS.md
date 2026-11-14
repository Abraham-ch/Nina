# NINA 0.3: processed global archive

The application uses a processed and verified global database. The MVP scope is **2025–2026**. The nine files in `source/` (on the original machine, `data_abraham/`) cover detections from **5 November 2025 to 13 November 2026**, depending on the instrument; the global snapshot of 14 November downloaded earlier is also kept.

## Data loaded

- **59,440,077 unique observations in the active database.**
- **57,332,047 new rows** from the team's global sources.
- **9 verified files**, equivalent to 23.54 GB of originals.
- **18,855 technical duplicates** discarded and **19 invalid rows** recorded with a reason.
- Landsat was excluded as an identified file; the scope is MODIS and VIIRS.

| Source | New rows loaded |
|---|---:|
| MODIS Terra + Aqua | 3,474,789 |
| VIIRS S-NPP | 17,456,430 |
| VIIRS NOAA-20 | 18,586,456 |
| VIIRS NOAA-21 | 17,814,372 |

The database total also includes the 2,108,030 observations from the previous delivery. Counts are observations per instrument; they do not represent distinct individual fires.

## Size and execution

DuckDB database: **2.24 GB**. Parquet copy: **1.87 GB**, with the same 59,440,077 rows. The originals are kept in `source/` (on the original machine, `data_abraham/`); they were not copied to the client or uploaded to Git.

The import uses two DuckDB query workers and a 1 GB memory limit per ingest connection, processing files and months in turns. Queries use a 2 GB limit by default. The map delivers at most 10,000 points, and the comparator 8,000 per instrument; counts and exports use all selected rows.

## Queries checked outside Peru

July 2026, VIIRS NOAA-20, over the Natural Earth reference geometries:

| Territory | Detections |
|---|---:|
| Brazil | 39,356 |
| Australia | 124,368 |
| Indonesia | 24,028 |
| United States | 92,794 |
| D. R. of the Congo | 364,618 |

In each case the map total was checked to match the analysis. The Parquet copy was verified against the database and no duplicate identifiers were found. The hashes of the nine originals and the balance of accepted and excluded rows were checked. The 33 backend tests, the web build and the nine lint and type tasks of the monorepo passed.

The API and the browser were also verified with the active database: global calendar, counts, point sample, comparison outside Peru, CSV export, manifest, explanation and mobile layout. Earlier months that only have Peruvian regional records do not fill the global calendar once global batches exist.

## Open and reproduce

From the repository root:

```powershell
.\start-nina.ps1
```

Open `http://127.0.0.1:8000/`. The main entry opens the global calendar. The initial selection is July 2026 with NOAA-20; country, month or instrument can be changed. The real period and files appear under Sources.

Local reports are in `data/global-import.json` and `data/release-world-v0.3.json`. The previous version of the database is kept in `data/backups/before-world-*/`. [Scope decision and processing commands](GLOBAL_SCOPE.md).

## Limits that still apply

The available global period does not reach five reference years; global medians or anomalies are not invented. The earlier Peruvian history is kept as a regional set.

Record dates do not certify observation opportunities or the absence of clouds. The calendar keeps partial or unknown-integrity states and does not turn unsupported areas into zeros. Global scientific harmonization and its validation remain pending; the calibration experiment is still limited to the Peruvian case.
