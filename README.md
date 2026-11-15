# NINA · version 0.3 · The memory of fire

Global atlas with CesiumJS, a React/TypeScript interface, a FastAPI API and DuckDB queries. It uses real NASA FIRMS data and NASA GIBS cartography. The territory and period selection connects the viewer, the calendar, the comparison and the evidence. [Global status of 0.3](docs/GLOBAL_STATUS.md), [scope and processing](docs/GLOBAL_SCOPE.md).

**The problem NINA solves, with its evidence: [docs/PROBLEM.md](docs/PROBLEM.md).** Harmonization pipeline and backend: [status, validation and limits](docs/BACKEND_STATUS.md). UX/UI integration: [harmonized product contract](docs/HARMONIZED_CONTRACT.md). The method lives in [`packages/nina/`](packages/nina/README.md) and runs offline; the server only reads its output ([ADR 0004](docs/adr/0004-offline-harmonization-pipeline.md)).

Project for the **NASA Space Apps Challenge**: harmonize MODIS and VIIRS fire detections to answer whether a fire season is really unusual.

## Open the application

On Windows, with Python 3.14 and Node.js 22, from the repository root:

```powershell
.\setup-nina.ps1
.\start-nina.ps1
```

Open **http://127.0.0.1:8000**. Interactive API documentation: **http://127.0.0.1:8000/docs**. Stop with Ctrl+C. Use a single server process, because the DuckDB database is written from that process.

To also download Peru's public history: stop the server and run `.\setup-nina.ps1 -DownloadData`.

If the local policy does not allow PowerShell scripts, the equivalent commands are:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd web
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe scripts/bootstrap_data.py
.\.venv\Scripts\python.exe -m nina.ingest
.\.venv\Scripts\python.exe -m nina.science
```

Docker alternative: `docker compose up --build` (mounts `data/`; not declared as tested).

The downloader uses the real index published by FIRMS, checks size and SHA-256 and resumes per file. Imports are idempotent. Do not download or import from another instance while the server is handling writes: use the import/update interface or stop it first.

## Local data

| Path | Content | In Git |
|---|---|---|
| `source/` | All FIRMS originals. At the root, the team's static files (`fire_archive_*.json`, `fire_nrt_*.json`, `*.csv`, ZIP): default input of `scripts/import_global.py`, as global scope (`NINA_SOURCE_DIR`) | No |
| `source/downloads/` | What arrives through the FIRMS API (`/api/acquisitions`, `/api/sync`), Peru's history (`bootstrap_data.py`) and CSVs uploaded from the interface. It lives in a subfolder because these are per-area scopes: this way they are not re-imported as global | No |
| `data/` | Derived files: `nina.duckdb` database, Parquet, caches, models and exports (`NINA_DATA_DIR`) | Only `data/boundaries/` |
| `.env` | Credentials and local configuration (copy from `.env.example`) | No |

Import the team's global archive from `source/` (with the server stopped or into a staging database):

```powershell
.\.venv\Scripts\python.exe -u scripts/import_global.py --data-dir data/world-build --start-year 2025 --end-year 2026
.\.venv\Scripts\python.exe -u scripts/verify_world.py --data-dir data/world-build --refresh-parquet
```

## What works

- Landing page that introduces the problem with a year of real detections in Peru, and a bilingual interface (English by default, Spanish available).
- 3D global globe and 2D view, real NASA GIBS tiles with a local cache and a reference image available offline.
- Selection of reference countries, all of Peru, its divisions, WGS84 coordinates and drawn polygons. Countries: Natural Earth 110m; a generalized selection, not a certification of official boundaries.
- MODIS Aqua/VIIRS comparison in one scene with a shared camera and period. Original observations are separated by color and shape; the slider works with the keyboard.
- Monthly history by instrument and platform, day/night and detection type.
- Descriptive comparison against the median of the same month over up to ten previous years, with a minimum of five eligible years.
- Distinction between unavailable data, partial records and archive zeros. The anomaly of partial periods is omitted.
- Map with real coordinates, with a deterministic sample when there are many points. The export keeps every row of the selection. On mobile, the calendar uses months per collapsible year.
- Export of the series and detections as CSV, JSON manifest, TXT report and SVG chart.
- Exploratory Poisson and simple-factor calibrations, with held-out years and regions.
- Substitution experiment: reveal the held-out Aqua reference and the error of an estimate. Case validated as software on the Peruvian archive, without claiming a final scientific harmonization.
- Local assistant that queries the results and answers with facts and references. There is an optional adapter for a compatible LLM provider; the figures stay under the server's control.
- Analytical assistant for the harmonized record (`/api/analyst`): tools over the territorial report, the department comparison and the validation results; every figure in an answer is checked against the tool results. Deterministic by default, Claude when `ANTHROPIC_API_KEY` is set ([docs/ANALYST.md](docs/ANALYST.md)).
- Territorial technical report (printable A4) and a priority table of Peru's departments ([docs/TERRITORIAL_REPORT.md](docs/TERRITORIAL_REPORT.md)).
- Recent global download and per-area monthly download through MAP_KEY, as background jobs in windows of up to five days. Product, dates and scope are verified; partial months keep their state.
- Import of FIRMS CSVs by geographic scope and spatial reconciliation of standard/provisional products. Reads and exports keep a consistent revision during local ingestion.
- Guided tour to present the problem, compare observers and review a real experiment; platform guide for newcomers; shareable links with the analysis configuration.

## Current global archive

The active database has **59,440,077 observations**, after loading nine global files from the team. The chosen period is **2025–2026**: the new originals contain data from 5 November 2025 to 13 November 2026 depending on the product, and the global snapshot of 14 November downloaded earlier is kept. [Figures by source and verified queries](docs/GLOBAL_STATUS.md).

Processing is not limited to Peru. The map, the calendar, the comparison and the exports query this global database. The earlier Peruvian history remains available as a regional set. Originals, the database and Parquet stay outside Git.

## Data loaded in the previous 0.2 delivery

Version 0.2 contains **2,108,030 unique detections**, from **57 loaded files** and **169,096,847 bytes of CSV**:

| Archive scope | Loaded window | Files | New rows |
|---|---|---|---|
| Peru | 2000–2025, depending on instrument | 48 | 2,034,899 |
| Global | 14 Nov 2026, NRT snapshot | 3 | 49,410 |
| Rectangle containing Australia | September 2025, MODIS SP | 6 | 23,721 |

The exact Australia selection with the Natural Earth geometry contains **12,934 Aqua observations** in September 2025. The downloaded files also include Terra and records of the bounding rectangle that fall outside the country geometry; those totals are not confused.

**The full global history is not downloaded yet.** It can be extended by month/area from Sources. The globe offers global navigation and shows the windows actually loaded; it does not turn gaps into zero or extrapolate the Peruvian model to the world.

The Peruvian annual subset keeps its **48 files and 163,067,831 bytes**:

| Source | Unique rows loaded | Published years downloaded |
|---|---|---|
| MODIS Terra + Aqua | 358,529 | 2000–2025 |
| VIIRS S-NPP | 1,047,073 | 2012–2025 |
| VIIRS NOAA-20 | 629,297 | 2018–2025 |

The Peruvian annual archive starts on 1 Nov 2000 and ends on 31 Dec 2025. NOAA-21 and 2026 were already loaded through the global API, not through that annual index. Standard and NRT windows stay identified.

The boundaries come from an identified version of geoBoundaries gbOpen, source Wikimedia Commons, 2008 representation and the Public Domain license stated in the metadata. The set contains 26 divisions and is not a certification of the current administrative boundaries of the Peruvian State. There are **5,452 detections** in the national archive without assignment to that geometry; they are kept in the national total.

Inventory, hashes and sources are in `data/inventory.json`, `data/processed/*.json` and `data/boundaries/provenance.json`. Parquet files are in `data/processed/observations.parquet`. The CSV size does not include the analytical database, Parquet, dependencies, caches or L2 products.

## Scientific scope of version 0.2

This is a **functional version of global observation, selective acquisition and exploratory Peruvian calibration**. Harmonization with control for clouds, exposure and geometry **is not validated yet**. No coverage percentage or invented interval is shown. The geographic extent of the viewer does not automatically extend the validity of the model.

The lab models use monthly archive counts: training in 2018–2022, validation in 2023 and testing in 2024–2025, with held-out regions. Only positive months of the input instrument contribute pairs; the set of valid opportunities has not been rebuilt. That is why the fit metrics do not prove recovery of unobserved fire or unbiased trends. Model exploration is limited to divisions of the set and to the 2018–2025 period; it is not applied to arbitrary polygons and no corrected national series is claimed.

Calendar months are grouped in **UTC** in this version. Selection of the `America/Lima` civil calendar is not offered yet. Anomalies are descriptions of observed counts of the same selection; they do not imply statistical significance or future fire risk.

The pending stage of the challenge requires downloading/aligning masks and geolocation, building valid opportunities and evaluating the harmonization at that scale. `scripts/inventory_l2.py` already queries CMR metadata and stores identified samples for the products found; it is not an exhaustive inventory or an authenticated downloader of the scientific products. Gaps are not replaced by physical zeros.

## Optional credentials

Copy `.env.example` to `.env` and configure the needed variables locally. Never include `.env` in Git or publish keys.

- `FIRMS_MAP_KEY`: enables the catalog, the global MODIS/NOAA-20/NOAA-21 snapshot and the per-area monthly download. `/api/sync` keeps compatibility with the earlier Peruvian client; the new routes are `/api/acquisitions` and `/api/acquisitions/month`.
- `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`: reserved for the next step of authenticated scientific download; version 0.2 does not download or process L2 automatically.
- `NINA_LLM_BASE_URL`, `NINA_LLM_API_KEY`, `NINA_LLM_MODEL`: enable the language adapter. Without them, the assistant keeps deterministic answers backed by the analysis. The optional provider only receives the question, the role and the results summary of the selected analysis; it does not receive NASA credentials or the full archive.

Restart the server after changing `.env`.

## Verification and development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd web
npm.cmd run build
npm.cmd run dev
```

CI (`.github/workflows/ci.yml`) runs the Python tests and the web build.

## Repository

| Path | Content |
|---|---|
| `nina/` | Python package: FastAPI API (`main.py`), ingestion, queries, exploratory calibration, assistant |
| `web/` | React + Vite + CesiumJS interface |
| `scripts/` | Download, import, verification and OpenAPI export |
| `tests/` | `pytest` tests |
| `design/`, `nina-demo.html` | Design direction and static demo |
| `openapi.json` | API contract, generated with `scripts/export_openapi.py` |
| `AGENTS.md` | Rules for agents and technical specification (current state + harmonization target) |
| `WORK_PLAN.md` | Work plan for 3 people: roles, file ownership, phases |
| `docs/` | Status, architecture, data sources, acceptance criteria, target contract, ADRs and `reference/` |

## Notice

Data from NASA FIRMS. Because of their spatial resolution, FIRMS does not recommend these data for tactical or local-scale decisions: this tool provides **historical context**. See the [FIRMS disclaimer](https://www.earthdata.nasa.gov/data/tools/firms).
