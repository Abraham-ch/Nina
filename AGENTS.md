# AGENTS.md — Harmonized fire activity calendar (MODIS + VIIRS)

> Guide for coding agents (and people) working in this repository.
> Read it fully before changing code. If an instruction here conflicts
> with a deeper `AGENTS.md` (e.g. `web/AGENTS.md`), the one closest to the edited file prevails.
>
> **Current state vs. target.** The working code is the **NINA 0.3 MVP** (repo root: `nina/` + `web/`):
> FIRMS observations per instrument, DuckDB queries and **exploratory** calibration. Sections §5–§11 describe
> the **target harmonization**; where the MVP and those sections differ in technology or structure, **the MVP rules**
> (§3, §4) and the target is reached by evolving the MVP, not by creating a parallel structure.

---

## 1. Purpose

Build a **coherent time series of hotspots (2000 → today)** combining:

- **MODIS C6.1** (Terra/Aqua, ~1 km): long series, since 2000.
- **VIIRS 375 m C2** (S-NPP, NOAA-20, NOAA-21): more detail and continuity, since 2012.

and serve it in a **web application** where the user chooses **region + date range** and gets:

- an **activity calendar** (year × month, color scale),
- time series, anomalies and a ranking of years,
- **CSV download** of the hotspots and of the query aggregates.

The project has two stages:

| Stage            | What it produces                                                                    | Where it lives                              |
| ---------------- | ----------------------------------------------------------------------------------- | ------------------------------------------- |
| 1 · Harmonization | Harmonized dataset: after this stage **the source sensor is no longer relevant**   | `nina/` (ingestion, `science.py`), `scripts/` |
| 2 · Web app      | API + frontend (today: observations per instrument; target: harmonized dataset)     | `nina/main.py`, `web/`                      |

The diagram `docs/architecture/calendario_incendios_arquitectura.excalidraw` shows the **original design** (monorepo, no longer
current). The current architecture is in §4 and in `docs/ARCHITECTURE.md`.

---

## 2. Rules for agents (mandatory)

1. **Never** add or concatenate counts from different sensors (MODIS/VIIRS) as if they were a single series without the
   validated calibration (§10). Observations are always shown identified by instrument/platform. Sensor-specific
   logic (origin, normalization, precedence) lives in `nina/ingest.py`, `nina/global_ingest.py` and
   `nina/remote.py`; `nina/main.py`, `nina/analytics.py` and `web/` do not reimplement it.
2. **Never** commit data: `source/` and `data/` are in `.gitignore` (only `data/boundaries/` is versioned).
   Tests create small synthetic data in temporary directories (see `tests/`).
3. **Never** silently drop a row: every rejected row is counted and recorded with a reason
   (`rejected`, `duplicates`, `excluded_files`, `qa_reason`) in the import report (§9.4).
4. All times are stored in **UTC**. Conversion to local time only happens in the API or the UI.
5. **Gap ≠ partial ≠ zero.** A period without data is never returned or painted as 0 hotspots (§5.4).
6. Any change to the **calibration/harmonization method** (`nina/science.py`, filters, grid) requires an ADR in
   `docs/adr/` and a version bump.
7. API changes (`nina/main.py` and models in `nina/analytics.py`) → regenerate `openapi.json` with
   `scripts/export_openapi.py` and update `web/src/types.ts` / `web/src/api.ts` in the same PR.
8. Keep the **FIRMS legal notice and citation** (§11) in the UI and in every export.
9. **A single process writes the DuckDB database** (`data/nina.duckdb`): do not run imports against the database the
   server uses; use `--data-dir data/<staging>` or stop the server.
10. Before finishing a task: `.\.venv\Scripts\python.exe -m pytest -q` and `npm.cmd --prefix web run build`.
    Do not deliver with failing tests or a failing build.
11. Processing changes (`nina/ingest.py`, `global_ingest.py`, `science.py`, `scripts/`) are checked against
    **`docs/ACCEPTANCE_CRITERIA.md`**; criteria not implemented are recorded as `pending`, never as met.

---

## 3. Repository structure and configuration

A single project (no pnpm/turbo/uv monorepo): **Python 3.14 + pip** for the server and **Node 22 + npm** for the
interface. FastAPI serves the API and also the built interface (`web/dist/`).

### 3.1 Folder tree

```
Nina/
├── nina/                     # Python package (server + processing)
│   ├── main.py               # FastAPI: /api/* routes, serves web/dist
│   ├── config.py             # ROOT, .env, NINA_DATA_DIR → data/
│   ├── store.py              # DuckDB: schema (observations, batches, analyses…), locking and atomic reads
│   ├── ingest.py             # FIRMS CSV import by scope (Peru), SP/NRT reconciliation
│   ├── global_ingest.py      # global JSON/CSV import with bounded memory (excludes Landsat)
│   ├── remote.py             # FIRMS client (MAP_KEY) and GIBS imagery; credentials only on the server
│   ├── analytics.py          # analysis: calendar, comparison, evidence, exports
│   ├── science.py            # exploratory calibration (Poisson / simple factor)
│   ├── harmonized.py         # /api/harmonized/* routes: read the packages/nina Parquet product (no calibration)
│   └── assistant.py          # deterministic assistant + optional LLM adapter
├── web/                      # React + Vite + TS + CesiumJS (npm, package-lock.json)
│   ├── src/                  # App, Globe, Calendar, DataPanel, Dialog, Experiment, Tour, i18n, landing/, api.ts, types.ts, export.ts
│   ├── public/assets/        # countries (Natural Earth), attribution, reference image, landing summary
│   └── scripts/              # asset preparation (Cesium, geography)
├── packages/nina/            # offline harmonization pipeline (H3 + uv, Python 3.12); see ADR 0002–0004
├── scripts/                  # bootstrap_data, import_global, sync_global, verify_*, export_openapi, inventory_l2, build_landing_data…
├── tests/                    # pytest
├── design/ · nina-demo.html  # design direction and static demo
├── docs/                     # status, architecture, sources, ACCEPTANCE_CRITERIA, API_CONTRACT (target), adr/, reference/
├── notebooks/                # exploration; nothing here is imported by the server
├── data/                     # gitignored except boundaries/: derived files (nina.duckdb, processed/, models/, exports/, catalog/, tiles/)
├── source/                   # gitignored: originals. Root = the team's static files (fire_archive_*.json, fire_nrt_*.json, *.csv, ZIP)
│   └── downloads/            #   downloads through the FIRMS API, Peru's history and uploaded CSVs (config.RAW)
├── openapi.json              # generated with scripts/export_openapi.py (do not edit by hand)
├── requirements.txt · requirements.lock.txt · pytest.ini
├── Dockerfile · compose.yaml · .dockerignore
├── setup-nina.ps1 · start-nina.ps1
├── .github/workflows/ci.yml  # pytest + web build
└── .env.example · .gitignore · .editorconfig · .nvmrc (22) · .python-version (3.14)
```

### 3.2 Environment

- Python: `.venv/` at the root (`py -3.14 -m venv .venv`), dependencies pinned in `requirements.lock.txt`.
  New dependency → add it to `requirements.txt` and regenerate the lock in the same PR.
- Web: `web/package-lock.json`. New dependency → `npm.cmd --prefix web install <pkg>`.
- Configuration: `.env` at the root (copy from `.env.example`). `NINA_DATA_DIR` and `NINA_SOURCE_DIR` are resolved relative
  to the root. Originals always in `source/` (`config.SOURCE`; downloads in `config.RAW` = `source/downloads/`),
  derived files always in `data/` (`config.DATA`).

### 3.3 Organization rules

- HTTP routes in `nina/main.py`; query logic in `nina/analytics.py`; database access only through `nina/store.py`.
- Processing and import in `nina/ingest.py` / `global_ingest.py`; console tasks in `scripts/` only call
  functions from `nina/`.
- Reference files for the target method (gaps, sensor lifecycle, input schema, legal texts):
  `docs/reference/`.
- Generated files (`openapi.json`, `web/dist/`) are not edited by hand.
- Technologies from the earlier plan that are **not** used (PostGIS, Redis, MinIO, Martin, Prefect, pnpm/Turborepo):
  they are only brought in with an ADR that justifies the change against the MVP. **H3 and uv** are used only in
  `packages/nina/` (ADR 0002 and 0004); the server does not import that package, it only reads its Parquet output.

---

## 4. Architecture

```
 NASA FIRMS (SP archive + NRT, MAP_KEY API) ──┐      scripts/ (bootstrap, import_global, sync_global)
 source/ (team originals) ────────────────────┼────► nina/ingest.py · nina/global_ingest.py · nina/remote.py
 geoBoundaries · Natural Earth · NASA GIBS ───┘                      │
                                                                     ▼
                                              DuckDB data/nina.duckdb  (+ Parquet in data/processed/)
                                                                     │
                                       nina/analytics.py · nina/science.py · nina/assistant.py
                                                                     │
                                              nina/main.py (FastAPI /api/* + static web/dist)
                                                                     │ JSON · CSV · SVG
                                                                     ▼
                                              web/ (React + CesiumJS) → emergency managers
```

| Component     | Technology                                         | Responsibility                                        |
| ------------- | -------------------------------------------------- | ----------------------------------------------------- |
| Processing    | Python 3.14, DuckDB, NumPy/SciPy, Shapely          | Ingestion, normalization, SP/NRT reconciliation, §6–§10 |
| Database      | DuckDB (local file) + Parquet                      | Observations, batches, analyses, jobs                 |
| API           | FastAPI + Uvicorn                                  | `/api/*` routes (§12); a single process writes the database |
| Frontend      | React + Vite + TS + CesiumJS                       | §13                                                   |
| Deployment    | Local (`start-nina.ps1`) or Docker (`compose.yaml`) |                                                      |
| CI            | GitHub Actions                                     | pytest + web build                                    |

---

## 5. Data sources (NASA FIRMS)

### 5.1 Download naming

Each instrument arrives in its own ZIP, whose name identifies the origin:

| ZIP prefix            | Instrument / satellite              | Use in the project                                 |
| --------------------- | ----------------------------------- | -------------------------------------------------- |
| `DL_FIRE_M-C61_<id>`  | MODIS Collection 6.1 (Terra + Aqua) | ✅                                                 |
| `DL_FIRE_SV-C2_<id>`  | VIIRS 375 m · S-NPP                 | ✅                                                 |
| `DL_FIRE_J1V-C2_<id>` | VIIRS 375 m · NOAA-20 (JPSS-1)      | ✅                                                 |
| `DL_FIRE_J2V-C2_<id>` | VIIRS 375 m · NOAA-21 (JPSS-2)      | ✅                                                 |
| `DL_FIRE_LS_<id>`     | Landsat 30 m                        | ❌ **Exclude** (not part of the harmonization)     |

Each ZIP may contain CSV (`fire_*.csv` + `Readme.txt`) or Shapefile
(`.dbf .prj .shp .shx .cpg`). **The canonical input format of the pipeline is JSON (§6)**; the
CSV/SHP readers convert to that format before validating.

### 5.2 NRT vs. standard files

| File                   | Product     | Quality        | Notes                                                                             |
| ---------------------- | ----------- | -------------- | --------------------------------------------------------------------------------- |
| `fire_archive_M-C61_*` | MCD14ML     | Standard (UMD) | Replaces the NRT ~3 months later                                                  |
| `fire_nrt_M-C61_*`     | MCD14DL     | NRT (LANCE)    | Provisional                                                                       |
| `fire_archive_SV-C2_*` | VNP14IMGTML | Standard (UMD) | Replaces the NRT ~3 months later                                                  |
| `fire_nrt_SV-C2_*`     | VNP14IMGTDL | NRT            | Provisional                                                                       |
| `fire_nrt_J1V-C2_*`    | VJ114IMGDL  | NRT            | The Readme says there is no standard product, but **the API already offers `VIIRS_NOAA20_SP`** |
| `fire_nrt_J2V-C2_*`    | VJ214IMGDL  | NRT            | NRT only (check in `data_availability`)                                           |

> Download URLs, API and limits: see **`docs/DATA_SOURCES.md`**.

Consequences you **must** implement:

- Detect `quality_level ∈ {standard, nrt}` from the **file name** (`fire_archive_` / `fire_nrt_`)
  and, as a fallback, from the `version` field (contains `NRT` → `nrt`).
- **Precedence rule**: for the same `(satellite, acq_date)`, if standard data exist, the
  NRT data are dropped (`qa_reason = "superseded_by_standard"`).
- `is_provisional` is computed with the real last standard date of each sensor, according to `/api/data_availability`.
  The delay is about 3 to 5 months depending on the source. A weekly job replaces NRT with standard data.
- NOAA-20 and NOAA-21 quality is taken from the real source (`_SP` = standard, `_NRT` = nrt), not from a fixed rule.
- A request without hotspots returns a CSV with only a header or an empty DBF. **It is not an error**:
  record it as `0 rows` and continue.

### 5.3 Expected temporal coverage

| Satellite     | Coverage in FIRMS            | Note                                                                                          |
| ------------- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| MODIS Terra   | 1 Nov 2000 → today           | The only morning overpass. NASA recommends migrating away from MODIS                          |
| MODIS Aqua    | Jul 2002 → today             |                                                                                               |
| VIIRS S-NPP   | 20 Jan 2012 → **2 Nov 2026** | ⛔ No new data since 2 Nov 2026 13:00 UTC. Reference for the MODIS ↔ VIIRS calibration        |
| VIIRS NOAA-20 | 1 Apr 2018 → today           | **Reference VIIRS sensor from 2 Nov 2026** (S-NPP ↔ NOAA-20 bridge, see SRC-02)               |
| VIIRS NOAA-21 | 17 Jan 2024 → today          | Continuity backup (NRT only)                                                                  |

A satellite's end of mission is recorded in `docs/reference/sensor_lifecycle.yaml` and does not count as a gap.

Do not hard-code these dates as truth: the pipeline computes the real coverage
(`min/max(acq_date)` per satellite) and stores it in the `coverage` table (§7.3).

### 5.4 Known MODIS gaps (FIRMS Readme + MODIS C6/C6.1 user guide)

| Period                                         | Situation                                             | Source      |
| ---------------------------------------------- | ----------------------------------------------------- | ----------- |
| before 2000-11-01 (Terra)                      | Hardware and calibration failures: **exclude**        | Guide §7.2.1 |
| September 2000 (Terra)                         | Instrument inoperative                                | Guide §8.3.3 |
| late June → early July 2001                    | Missing data                                          | Readme      |
| 2002 (throughout the year)                     | Intermittent missing data                             | Readme      |
| 2007, from mid-August                          | Missing data                                          | Readme      |
| 21 Apr 2009 (partial) and 22 Apr 2009 (complete) | Missing data                                        | Readme      |
| 16 Aug 2020 → 02 Sep 2020 (Aqua)               | FMU failure; coverage limited to direct broadcast     | Guide §7.2.4 |

In addition, FIRMS warns that there may be **erroneous data**. Implement:

- `docs/reference/known_gaps.yaml` with those periods (exact dates to be confirmed with the
  real daily count; mark as a gap any day with 0 global detections for the satellite).
- In the aggregates, a day/month without data is marked `data_gap = true`. **It is not the same as 0 hotspots.**
  The UI must show it with hatching or in grey, never as "no activity".
- Detection of quality anomalies: days whose global count deviates more than 5 robust deviations
  (MAD) from the 31-day rolling median → `qa_flag = "suspicious_day"` in the report (they are not deleted).

### 5.5 Projection

All input comes in **geographic WGS84 (EPSG:4326)**. It is stored in EPSG:4326; area
computations use an equal-area projection (EPSG:6933) or H3.

---

## 6. Input contract: JSON (array of objects)

The pipeline accepts **a `.json` file whose content is an array of objects**, one object per hotspot.
Real example (MODIS, standard):

```json
[
    {
        "latitude": -26.9523,
        "longitude": 32.6844,
        "acq_date": "2025-11-05",
        "acq_time": "0000",
        "scan": 2.5,
        "confidence": "48",
        "daynight": "N",
        "bright_t31": 287,
        "track": 1.5,
        "type": "0",
        "frp": 24.9,
        "instrument": "MODIS",
        "version": "61.03",
        "satellite": "Aqua",
        "brightness": 302.3
    }
]
```

VIIRS example (same contract; the brightness fields and confidence change):

```json
[
    {
        "latitude": -12.0464,
        "longitude": -77.0428,
        "acq_date": "2025-11-05",
        "acq_time": "0618",
        "scan": 0.39,
        "track": 0.36,
        "confidence": "n",
        "daynight": "N",
        "bright_ti4": 330.1,
        "bright_ti5": 290.4,
        "frp": 3.2,
        "instrument": "VIIRS",
        "version": "2.0NRT",
        "satellite": "N"
    }
]
```

### 6.1 Fields

Types are **as they arrive** (note: several numeric fields arrive as _strings_).

| Field        | Raw type             | MODIS                                 | VIIRS                                       | Description / validation                                                                                                                                 |
| ------------ | -------------------- | ------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `latitude`   | number               | ✅                                    | ✅                                          | Pixel center. `-90 ≤ lat ≤ 90`                                                                                                                           |
| `longitude`  | number               | ✅                                    | ✅                                          | Pixel center. `-180 ≤ lon ≤ 180`                                                                                                                         |
| `acq_date`   | string `YYYY-MM-DD`  | ✅                                    | ✅                                          | Acquisition date in **UTC**                                                                                                                              |
| `acq_time`   | string `HHMM`        | ✅                                    | ✅                                          | **UTC** time, zero-padded (`"0000"`, `"0618"`). If it arrives as a number (`618`), pad to 4 digits                                                       |
| `scan`       | number               | ✅                                    | ✅                                          | Pixel size along the scan (km)                                                                                                                           |
| `track`      | number               | ✅                                    | ✅                                          | Pixel size along the track (km)                                                                                                                          |
| `confidence` | **string**           | `"0"`–`"100"`                         | `"l"` / `"n"` / `"h"`                       | See §9.2                                                                                                                                                 |
| `daynight`   | string               | ✅                                    | ✅                                          | `"D"` day, `"N"` night                                                                                                                                   |
| `brightness` | number               | ✅                                    | —                                           | MODIS: channel 21/22 brightness temperature (K)                                                                                                          |
| `bright_t31` | number               | ✅                                    | —                                           | MODIS: channel 31 brightness temperature (K)                                                                                                             |
| `bright_ti4` | number               | —                                     | ✅                                          | VIIRS: I-4 brightness (K). Some services deliver it as `brightness`                                                                                      |
| `bright_ti5` | number               | —                                     | ✅                                          | VIIRS: I-5 brightness (K). Some services deliver it as `brightness_2`                                                                                    |
| `frp`        | number               | ✅                                    | ✅                                          | Fire radiative power (MW). `≥ 0`                                                                                                                         |
| `type`       | **string**, optional | ✅*                                   | ✅*                                         | `"0"` presumed vegetation · `"1"` active volcano · `"2"` other static land source · `"3"` offshore. *Only in **standard** products; absent in NRT       |
| `instrument` | string               | `"MODIS"`                             | `"VIIRS"`                                   |                                                                                                                                                          |
| `version`    | string               | e.g. `"61.03"`, `"6.1"`, `"6.1NRT"`   | e.g. `"2"`, `"2.0NRT"`                      | Collection/version. Allows distinguishing the origin after combining files                                                                              |
| `satellite`  | string               | `"Aqua"`, `"Terra"` (or `"A"`, `"T"`) | `"N"` (S-NPP), `"N20"`/`"1"`, `"N21"`/`"2"` | Normalize with the map in §7.2                                                                                                                           |

### 6.2 Validator rules (`docs/reference/hotspot_input.schema.json`)

- Root: `type: array`, `items: object`. An empty array `[]` is **valid**.
- Required: `latitude, longitude, acq_date, acq_time, confidence, daynight, frp, instrument, satellite`.
- `additionalProperties: true` (FIRMS may add fields; they are kept in `raw_extra`).
- Per instrument: if `instrument = "MODIS"` → requires `brightness`; if `"VIIRS"` → requires `bright_ti4`
  (or its alias `brightness`).
- Read with **UTF-8** encoding; tolerate a BOM. The FIRMS `Readme.txt` contains badly encoded characters
  (`â€œ`): do not rely on parsing that file.

---

## 7. Normalized and harmonized schema

### 7.1 `hotspots_normalized` (normalization output, one row per detection)

| Column                | Type                                             | Origin / rule                                                                  |
| --------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| `hotspot_id`          | text (PK)                                        | Stable hash of `satellite_norm, acq_datetime_utc, round(lat,4), round(lon,4)`  |
| `acq_datetime_utc`    | timestamptz                                      | `acq_date` + `acq_time` (`HHMM`) in UTC                                        |
| `acq_date_utc`        | date                                             |                                                                                |
| `lat`, `lon`          | double                                           |                                                                                |
| `geom`                | geometry(Point, 4326)                            |                                                                                |
| `instrument`          | enum `modis \| viirs`                            |                                                                                |
| `satellite_norm`      | enum `terra \| aqua \| snpp \| noaa20 \| noaa21` | §7.2                                                                           |
| `quality_level`       | enum `standard \| nrt \| rt`                     | §5.2; `rt` = provisional RT/URT (SRC-05)                                       |
| `is_provisional`      | bool                                             | `nrt`/`rt` and a date after the sensor's last standard date                    |
| `confidence_raw`      | text                                             | Original value                                                                 |
| `confidence_class`    | enum `low \| nominal \| high`                    | §9.2                                                                           |
| `daynight`            | enum `D \| N`                                    |                                                                                |
| `frp_mw`              | double                                           |                                                                                |
| `bt_mir_k`            | double                                           | MODIS `brightness` / VIIRS `bright_ti4`                                        |
| `bt_tir_k`            | double                                           | MODIS `bright_t31` / VIIRS `bright_ti5`                                        |
| `scan_km`, `track_km` | double                                           |                                                                                |
| `hotspot_type`        | smallint null                                    | `type`; `null` if NRT                                                          |
| `version`             | text                                             | Original                                                                       |
| `source_file`         | text                                             | Name of the source file                                                        |
| `h3_cell`             | text                                             | H3 cell at `H3_RES` (§10)                                                      |
| `qa_flags`            | text[]                                           | §9                                                                             |

### 7.2 `satellite` normalization

```python
SATELLITE_MAP = {
    "Terra": "terra", "T": "terra",
    "Aqua": "aqua",   "A": "aqua",
    "N": "snpp", "NPP": "snpp", "Suomi NPP": "snpp",
    "N20": "noaa20", "1": "noaa20", "NOAA-20": "noaa20", "J1": "noaa20",
    "N21": "noaa21", "2": "noaa21", "NOAA-21": "noaa21", "J2": "noaa21",
}
```

A value outside the map → row rejected with `qa_reason = "unknown_satellite"` (and an alert in the report).
If the file name (`SV`, `J1V`, `J2V`, `M`) contradicts `satellite`, the file wins and
`qa_flag = "satellite_mismatch"` is added.

### 7.3 Target tables

> Today the database is DuckDB (`nina/store.py`: `observations`, `batches`, `analyses`, …). This table describes the
> target model of the harmonization; it is implemented in DuckDB unless an ADR says otherwise.

| Table / view          | Grain                               | Use                                                               |
| --------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `hotspots`            | detection (only rows that pass QA)  | Map, hotspot export                                               |
| `cell_day_activity`   | `h3_cell × date × satellite_norm`   | Basis of the harmonization                                        |
| `harmonized_cell_day` | `h3_cell × date`                    | **Table the app consumes** (§10.4)                                |
| `admin_regions`       | polygon                             | Region selector                                                   |
| `coverage`            | `satellite_norm`                    | `first_date`, `last_date`, `quality_level`                        |
| `data_gaps`           | `satellite_norm × date`             | Known and detected gaps                                           |
| `mv_region_month`     | materialized view                   | Precomputed calendars for administrative regions                  |
| `dataset_versions`    | version                             | `harmonization_version`, run date, validation metrics             |

---

## 8. Dates and time

- Source of truth: `acq_date` + `acq_time` in **UTC** → `acq_datetime_utc`.
- Default daily aggregation uses the **UTC date**. The API accepts `tz` (IANA, e.g. `America/Lima`)
  to regroup by local date; the monthly calendar barely changes, the daily one does.
- Global dataset range: from the first day with MODIS Terra data (≈ Nov 2000) to the last
  ingested day. The **climatology** uses **2001 → last complete year** by default (2000 is incomplete).
- Overlap period for calibration: **2012-01-20 → last day with standard S-NPP data**.
  NRT data are not used for calibration.
- Months with `data_gap` or `partial_coverage` on > 20 % of their days are excluded from the climatology and the year ranking.
- **Sampling bias**: according to the MODIS guide, series with intervals shorter than about 8 days have severe biases.
  The calendar is **monthly**; anomalies and rankings are only computed with aggregations of 8 days or more, and every
  daily output carries `sampling_bias_warning = true`.

---

## 9. Data quality (QA)

### 9.1 QA pipeline order

1. **Schema**: validate against the JSON Schema (§6.2). If it fails → `qa_reason = "schema_invalid"`.
2. **Ranges**: valid lat/lon, `frp ≥ 0`, `daynight ∈ {D,N}`, `acq_time` in 0000–2359,
   `acq_date` not in the future → `qa_reason = "out_of_range"`.
3. **Origin**: exclude Landsat (`qa_reason = "excluded_instrument"`).
4. **Standard > NRT precedence** (§5.2) → `superseded_by_standard`.
5. **Hotspot type** (only if `type` exists): keep `type = 0`. `1, 2, 3` → `non_vegetation_type`.
   Then, for **all** hotspots (including MODIS with `type = 0`, because some static sources are not
   flagged): apply `static_source_mask` → ~1 km cell with detections on **≥ 16 days of the same
   calendar year** (the guide's criterion for `type = 2`), urban area (MCD12Q1 class 13), surroundings of an
   active volcano or water.
6. **Confidence** (§9.2): `low` is excluded by default → `low_confidence`.
7. **Duplicates**: same `hotspot_id` → `duplicate`.
8. **Gaps and suspicious days** (§5.4): they do not remove rows; they are recorded in `data_gaps` and in the report.

### 9.2 Unified confidence

| Instrument | Raw value   | `confidence_class` |
| ---------- | ----------- | ------------------ |
| MODIS      | `0`–`29`    | `low`              |
| MODIS      | `30`–`79`   | `nominal`          |
| MODIS      | `80`–`100`  | `high`             |
| VIIRS      | `l`         | `low`              |
| VIIRS      | `n`         | `nominal`          |
| VIIRS      | `h`         | `high`             |

MODIS `confidence` arrives as a string (`"48"`): convert with `int()`; if not numeric → `schema_invalid`.
Confidence means different things in different regions: do not use it as a weight, only as a filter.

### 9.3 Target parameters (they will go in `nina/config.py`, overridable by environment variables; not implemented yet)

| Parameter                         | Default                                              |
| --------------------------------- | ---------------------------------------------------- |
| `MIN_CONFIDENCE_CLASS`            | `nominal`                                            |
| `KEEP_TYPES`                      | `[0]`                                                |
| `H3_RES`                          | `7` (≈ 5 km²)                                        |
| `PROVISIONAL_DAYS`                | `150` (only as a fallback if `data_availability` fails) |
| `FIRMS_MAX_DAY_RANGE`             | `5`                                                  |
| `STATIC_SOURCE_MIN_DAYS_PER_YEAR` | `16`                                                 |
| `STATIC_SOURCE_H3_RES`            | `8` (≈ 1 km)                                         |
| `VOLCANO_BUFFER_KM`               | `2`                                                  |
| `SERIES_START_DATE`               | `2000-11-01`                                         |
| `MIN_AGG_DAYS_FOR_ANOMALY`        | `8`                                                  |

### 9.4 QA report

Each run writes `data/reports/qa_<run_id>.json` with: rows read per file, rows accepted,
count per `qa_reason`, coverage per satellite, gap days and suspicious days. The job fails
if `schema_invalid / rows_read > 1 %`.

---

## 10. MODIS ↔ VIIRS harmonization

**Problem:** VIIRS (375 m) detects considerably more hotspots than MODIS (1 km) on the same fire, so
concatenating the raw counts creates an artificial jump in 2012.

### 10.1 Counting unit

Pixels are not counted. **Active cells** are counted: `active = 1` if the H3 cell (`H3_RES`) had
≥ 1 valid hotspot that day. This reduces resolution bias before calibrating.

### 10.2 Calibration (in the overlap)

1. Build `cell_day_activity` for MODIS (Terra + Aqua combined) and VIIRS (S-NPP; NOAA-20/21 only
   as continuity reinforcement after 2018, never for calibration).
2. Aggregate to `stratum × month`, where stratum = biome (or level-1 administrative region if there is no biome).
3. Fit, per stratum and calendar month, a model `VIIRS_equiv = f(MODIS)`:
    - by default: **robust ratio** (median of `VIIRS/MODIS` over cell-months with MODIS > 0);
    - configurable alternative: Poisson/NB regression or _quantile mapping_.
4. Store the coefficients in `data/harmonized/calibration_<version>.parquet`.

### 10.3 Validation (mandatory gate)

- Leave-one-year-out cross-validation over 2012 → last standard year.
- Metrics per stratum: relative bias, R², RMSE, Spearman correlation of the monthly seasonality.
- **Acceptance threshold**: |relative bias| ≤ 10 % and Spearman ≥ 0.8 in ≥ 80 % of the strata with data.
- If not met → the flow fails, does not publish and leaves the report in `data/reports/validation_<version>.json`.
- Optional: cross-check with MCD64A1 burned area.

### 10.4 Final product `harmonized_cell_day`

| Column                  | Description                                        |
| ----------------------- | -------------------------------------------------- |
| `h3_cell`, `date`       | Key                                                |
| `active_cells_equiv`    | 0/1 or a fraction, in "VIIRS equivalent" units     |
| `hotspot_count_equiv`   | Estimated VIIRS-equivalent hotspot count           |
| `source_mix`            | `modis_only` (2000–2011) · `viirs` · `modis+viirs` |
| `is_provisional`        | Inherited from NRT                                 |
| `data_gap`              | Bool                                               |
| `harmonization_version` | semver                                             |

- 2000–2011: MODIS transformed with the calibration.
- 2012-01-20 → 2026-11-02: observed VIIRS S-NPP (NOAA-20 fills days without S-NPP from 2018).
- 2026-11-02 → today: NOAA-20 adjusted with the S-NPP ↔ NOAA-20 bridge (NOAA-21 as a backup).
- The app does **not** expose `source_mix` in the main UI (only in "Dataset details").

---

## 11. Legal notice and citation (mandatory)

FIRMS asks that its disclaimer and citation be replicated or linked when redistributing the data.

- **UI**: permanent footer with the citation and a link to the disclaimer.
- **Visible warning** next to the calendar: because of their spatial resolution, FIRMS does not recommend using these
  data for **tactical or local-scale decisions**. The calendar is a tool for historical context.
- **Exports**: each CSV includes a `README.txt` (or a ZIP download) with the FIRMS citation, the dataset
  version, the filters used and the generation date.
- Texts: today in the interface (`web/src/`, in English and Spanish through `tr()`) and `web/public/assets/attribution.json`;
  the en/es reference version is in `docs/reference/firms_legal.json`. When changing them, keep them consistent across those places.

---

## 12. API (`nina/main.py`)

Source of truth: **`openapi.json`** (generated with `scripts/export_openapi.py`) and `http://127.0.0.1:8000/docs`.
`docs/API_CONTRACT.md` describes the **target contract** (`/api/v1`) of the harmonized version; it is not implemented.

| Method   | Route                                                                      | Use                                               |
| -------- | -------------------------------------------------------------------------- | ------------------------------------------------- |
| GET      | `/api/health`, `/api/status`                                               | Service and database status                       |
| GET      | `/api/catalog`, `/api/places`, `/api/regions`                              | FIRMS catalog, places and divisions               |
| GET      | `/api/imagery/blue-marble/{z}/{x}/{y}.jpg`                                 | GIBS tiles with a local cache                     |
| POST     | `/api/analyses`                                                            | Creates an analysis (territory + period + filters) |
| GET      | `/api/analyses/{id}`, `…/points`, `…/comparison`, `…/evidence`             | Result, points, comparison, evidence              |
| GET      | `/api/analyses/{id}/exports/{kind}`                                        | CSV, JSON manifest, TXT report, SVG               |
| POST     | `/api/assistant`                                                           | Assistant with evidence                           |
| GET/POST | `/api/models`, `/api/models/train`                                         | Exploratory calibrations                          |
| GET      | `/api/jobs`, `/api/jobs/{id}`                                              | Background jobs                                   |
| POST     | `/api/import`, `/api/sync`, `/api/acquisitions`, `/api/acquisitions/month` | FIRMS import and acquisition                      |
| GET      | `/api/experiments/substitution`                                            | Aqua substitution experiment                      |

### 12.1 Exported hotspot CSV (target)

Separator `,`, UTF-8 with BOM (for Excel), ISO-8601 dates:

```
hotspot_id,acq_datetime_utc,acq_date_local,lat,lon,frp_mw,confidence_class,daynight,quality_level,is_provisional,harmonization_version
```

`instrument` and `satellite_norm` are only included with `?include_source=true`.

---

## 13. Frontend (`web/`)

Today: a landing page (`web/src/landing/`) that introduces the problem with a year of real detections in Peru; a 3D/2D globe
with CesiumJS and GIBS tiles (`Globe.tsx`); country/Peru/division/polygon selection; monthly calendar (`Calendar.tsx`);
MODIS/VIIRS comparison; data panel and exports (`export.ts`); assistant (`Dialog.tsx`); substitution experiment
(`Experiment.tsx`); and a platform guide for newcomers (`Tour.tsx`). Requirements that stay as it evolves:

- **Calendar**: rows = years, columns = months; count mode (sequential scale) and anomaly mode (diverging, centered on 0).
    - `data_gap` → grey hatched cell; partial and provisional distinguishable; never a gap as 0.
    - Tooltip with count, reference median and anomaly. Accessible colors and an always-visible legend.
- **Time series**: in the daily view, a sampling-bias warning; months with partial coverage marked.
- **Downloads**: hotspot CSV, calendar CSV, SVG/PNG charts, with citation and warning (§11).
- API types only in `web/src/types.ts`, aligned with `openapi.json`. TypeScript `strict`.
- Bilingual interface: English by default and Spanish available, with every visible string through `tr(en, es)` from
  `web/src/i18n.ts`. The language is chosen with the EN/ES switch, `?lang=` or the saved preference.

---

## 14. Commands

```powershell
# Install (Python 3.14 + Node 22)
.\setup-nina.ps1                 # .venv + requirements.lock.txt + npm ci + web build
.\setup-nina.ps1 -DownloadData   # also downloads and imports Peru's public history

# Run
copy .env.example .env           # and fill in values
.\start-nina.ps1                 # http://127.0.0.1:8000 · API at /docs
npm.cmd --prefix web run dev     # interface in development mode (with the server running)
docker compose up --build        # Docker alternative (mounts data/)

# Data (import_global reads source/ by default)
.\.venv\Scripts\python.exe -u scripts/import_global.py --data-dir data/world-build --start-year 2025 --end-year 2026
.\.venv\Scripts\python.exe -u scripts/verify_world.py --data-dir data/world-build --refresh-parquet
.\.venv\Scripts\python.exe -m nina.ingest
.\.venv\Scripts\python.exe -m nina.science
.\.venv\Scripts\python.exe scripts/build_landing_data.py   # landing summary (reads the database read-only)

# Quality
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix web run build

# API contract
.\.venv\Scripts\python.exe scripts/export_openapi.py
```

---

## 15. Tests

- `tests/` (pytest): `test_nina.py`, `test_global_ingest.py`, `test_global_queries.py`. They create synthetic databases and files
  in temporary folders; they never read `source/` or `data/`.
- Every fix to ingestion, query or export logic adds or adjusts a test there.
- Target tests for the harmonization (add them when implementing it):
    - `acq_time "0000"` → `00:00 UTC`; `"618"` and `618` → `06:18 UTC`.
    - `confidence "48"` (MODIS) → `nominal`; `"29"` → `low`; `"h"` (VIIRS) → `high`.
    - Standard > NRT precedence for the same satellite and day.
    - NRT without `type` is not rejected by the schema.
    - Known gap days → `data_gap = true`, never `count = 0`.
    - Empty file → 0 rows, no exception.
    - The harmonization preserves the order of the years (rank correlation) in the overlap.
- Web: the build (`tsc -b && vite build`) is the minimum check.

---

## 16. Conventions

- Python: follow the style of the module you are editing; database access only through `nina/store.py`. New docstrings,
  comments and documentation are written in English.
- TypeScript: `strict: true`, no `any`, functional components.
- Commits: Conventional Commits (`feat(nina): ...`, `fix(api): ...`, `feat(web): ...`, `docs: ...`).
- Column and table names in English `snake_case`; UI text in English with its Spanish version through `tr()`.

## 17. Definition of done

- [ ] `pytest` and the web build green.
- [ ] `openapi.json` regenerated and `web/src/types.ts` updated if the API changed.
- [ ] ADR + new version if the calibration/harmonization method changed.
- [ ] FIRMS citation and warning present in the UI and exports.
- [ ] `docs/` updated when a user-visible behavior changes.
