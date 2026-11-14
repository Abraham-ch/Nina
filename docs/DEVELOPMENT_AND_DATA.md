# NINA 0.2: what was built and how the data are processed

The figures in this document correspond to delivery 0.2. The current version includes the global archive: [status 0.3](GLOBAL_STATUS.md) and [ingestion period and method](GLOBAL_SCOPE.md).

Document of the implemented state, reviewed on **14 November 2026** against the code, the verification reports and the local API. It describes the application served at `http://127.0.0.1:8000`; the file `nina-demo.html` corresponds to the earlier prototype with simulated data.

## 1. Direct answer: raw or processed data?

**NINA shows real NASA FIRMS data that have gone through processing inside NINA.** It does not just draw an API response directly. It downloads files, keeps the originals, validates and normalizes records, removes technical duplicates, queries a local database and computes results by territory and period.

In addition, the FIRMS CSV is already a detection product generated from satellite observations. It is neither the raw sensor signal nor an unprocessed image. NASA uses MODIS and VIIRS observations to detect active fires and thermal anomalies. [Official FIRMS description](https://firms.modaps.eosdis.nasa.gov/).

It helps to distinguish four levels:

| Level | What it contains | Situation in NINA |
|---|---|---|
| Original received | FIRMS CSV, annual or downloaded through the API | Kept in `data/raw/`, with a SHA-256 hash |
| Normalized record | Coordinates, date, platform, FRP, confidence and provenance in a common schema | Stored in DuckDB; keeps the link to the file |
| Analytical result | Monthly counts, spatial selection, historical median and descriptive differences | Computed by NINA from observed records |
| Model estimate | Monthly count estimated relative to MODIS Aqua from VIIRS | Experimental, limited to the Peruvian case; separate from the detections |

**Processing and organizing the data is not the same as having finished the scientific harmonization between MODIS and VIIRS.** Correction for observation opportunities, clouds and geometry is still pending.

### What each visible element represents

| Element | Where it comes from | How to read it |
|---|---|---|
| Atlas points | FIRMS records normalized and filtered by area, month and sensor | Observed detections; not points invented by a model |
| Number of detections | Count of all rows that match the selection | Not equivalent to individual fires or burned area |
| Calendar | Monthly aggregation in UTC | Series of detections from the loaded archive |
| Historical median | Same month over up to ten previous eligible years | Descriptive reference for that selection; requires at least five years |
| Percentage difference | Comparison of the month against its median | Not a forecast or a risk measure |
| MODIS/VIIRS comparator | Two separate queries with the same territory and period | Shows differences between instruments; not a harmonized fusion |
| Lab estimate | Model trained with Peruvian counts | Computed result, identified as experimental |
| Reference revealed in the lab | Aqua count held out for the test | Real observation used to evaluate the fit; not the complete truth of existing fire |
| Globe background | NASA GIBS, layer `BlueMarble_NextGeneration`, and a local reference | Geographic reference image; **it does not change with the selected month or show live fires** |

## 2. How a FIRMS file is transformed

### Step 1. Acquisition and preservation

There are two main routes: annual historical files published per country and FIRMS Area API queries. CSVs can also be imported from the interface.

API acquisition first checks the availability of each product. A monthly download is split into windows of up to five days. For a country or polygon, FIRMS receives its bounding rectangle; the exact clip to the selected geometry happens at analysis time.

Each loaded file keeps its size, hash, source, dates, spatial scope and import time. An incomplete transfer is not recorded as an available window. The FIRMS key is used only on the server and is omitted from the exported provenance.

Code: [historical download](../scripts/bootstrap_data.py), [API acquisition](../nina/remote.py), [ingestion](../nina/ingest.py).

### Step 2. Validation and normalization

Ingestion checks valid geographic coordinates, date/time, platform and numeric fields. Rejected records are counted, with examples of the reason. FIRMS time is interpreted in UTC; this version has no grouping by Lima's civil calendar.

Source names are normalized: for example, NOAA-20 is represented internally as `viirs-jpss1`, and NOAA-21 as `viirs-jpss2`. MODIS keeps the split between Terra and Aqua.

The analytical table stores 16 fields: identifier, source, platform, acquisition, latitude, longitude, FRP, confidence, version, processing, day/night, type, Peruvian division, batch, scan and track. The original file also keeps the FIRMS columns that do not fit this schema.

**FRP and confidence are kept as product attributes. No physical FRP calibration is applied and MODIS and VIIRS confidence is not converted to a common probability.** No new fire detector is run on images either.

Code: `parse_row` in [nina/ingest.py](../nina/ingest.py).

### Step 3. Duplicates and revisions

The technical identity combines source, platform, date/time and coordinates expressed to six decimals. This avoids loading the same record twice when imports are repeated.

Nearby detections are not grouped to claim they belong to the same fire. Nor is a VIIRS point removed for being close to a MODIS one: they are different observations.

Provisional `NRT` and standard `SP` products are distinguished. Ingestion gives priority to the standard product within the corresponding spatial and temporal windows, to avoid adding the replaced provisional versions as new observations. This reconciliation is not a harmonization between instruments.

Code: `ingest_file` in [nina/ingest.py](../nina/ingest.py).

### Step 4. Territorial assignment and storage

Shapely assigns detections to the available Peruvian divisions. Global files keep records from other countries even without an assigned Peruvian division.

DuckDB is the database the application queries. The Parquet file is an analytical copy that is refreshed explicitly; it is not regenerated automatically with each download from the interface.

| Location | Content |
|---|---|
| `data/raw/` | Original CSVs downloaded or imported |
| `data/nina.duckdb` | Observations, batches, analyses and job states |
| `data/processed/*.json` | Ingestion reports per batch |
| `data/processed/observations.parquet` | Compressed analytical copy |
| `data/models/benchmark.json` | Coefficients, metrics and model identification |
| `data/catalog/` | Product availability queried from FIRMS |
| `data/tiles/` | Local cache of map images |
| `data/boundaries/` and `web/public/assets/` | Geometries and cartography information |

The Peruvian annual history keeps 5,452 detections without assignment to its administrative geometry; they remain in the national total. The total of global records without a Peruvian department must not be read as a geographic error.

Code: [nina/store.py](../nina/store.py), [nina/ingest.py](../nina/ingest.py).

### Step 5. Query and computation

A selection specifies scope, geometry or division, source, platform, years, month, day/night and detection type. For polygons, a rectangular filter is applied first and then an exact check against **the selected reference geometry**; that does not certify the precision of the real political boundaries.

Counts are computed over all selected rows, before visual sampling. The median uses the same month over up to ten previous years with an eligible monthly archive. At least five values are required.

The descriptive difference is computed as `100 × (value / median − 1)`. It is omitted if the month is partial, there is no sufficient median or the median is zero.

Code: [nina/analytics.py](../nina/analytics.py).

### Step 6. Presentation and export

The normal map delivers at most 10,000 points; the comparator at most 8,000 per instrument. If there are more records, the server selects a deterministic sample ordered by identifier. Responses distinguish `total` and `shown`.

**The sample affects the drawn points, not the monthly count.** It is not a statistical sample designed to infer spatial density: a visually empty area does not prove the absence of detections in the full set.

The observations CSV exports all normalized rows of the selected area and month, with their filters. Although the interface calls it "Original observations", **it is not a byte-for-byte copy of the NASA CSV**: those originals are in `data/raw/`. The export also does not automatically include other months or sensors outside the selection.

Code: `points_for_analysis` in [nina/analytics.py](../nina/analytics.py), exports in [nina/main.py](../nina/main.py) and the figure in [web/src/export.ts](../web/src/export.ts).

## 3. What "no data", "partial" and "zero" mean

| State | Meaning in this implementation |
|---|---|
| Not available | There is no output supported by the loaded windows or records for that selection |
| Partial archive | There are detections or an archive window, but no support to consider the month complete |
| Observed archive | The recorded windows cover the month and scope according to the system rules |
| Archive zero | The eligible monthly archive has no detections matching the filters |

Eligibility is derived from the dates of the annual files, the windows requested from the API or, in a manual import, the dates declared by whoever imports. **It does not measure how much territory was cloud-free or how many valid opportunities each sensor had.** An archive zero does not prove the physical absence of fire.

National dates are not attributed automatically to the world. Currently, a custom polygon inside Peru does not automatically inherit the whole national annual availability either: it may remain partial, conservatively.

Coverage percentage and interval fields stay empty when they have not been computed. They are not filled with demo figures.

## 4. How much real information is loaded

Cut-off of delivery 0.2 on 14 November 2026. The total was checked against `/api/status` while preparing this document.

| Loaded set | Window | Files | New detections |
|---|---|---:|---:|
| Peruvian archive | 2000–2025, depending on product | 48 | 2,034,899 |
| Global MODIS, NOAA-20 and NOAA-21 snapshot | 14 November 2026, NRT | 3 | 49,410 |
| Rectangle containing Australia, MODIS SP | September 2025 | 6 | 23,721 |
| **Total** | **Identified windows, not a continuous global history** | **57** | **2,108,030** |

The CSVs add up to **169,096,847 bytes**, about 169 decimal MB. The verified Parquet copy contains the same 2,108,030 rows and takes 67,353,689 bytes. These are sizes of these artifacts, not of the whole project.

Concrete processing example: **23,721 MODIS records** were downloaded for the Australian rectangle. Selecting the Australia polygon and only Aqua for September 2025 leaves **12,934 detections**. The totals differ because of the platform and geometry filters; not because the map invents or loses records.

The viewer has global scope and allows acquiring new months by area. **It does not yet contain the history of every country.** A one-day global snapshot does not equal a full month either.

Evidence: [delivery inventory](../data/release-v0.2.json), [version status](STATUS_V2.md).

## 5. What application was built

### Atlas and shared selection

The previous viewer was replaced by CesiumJS, with a 3D globe, 2D view and real cartography. The user can choose the world, Peru, its 26 reference divisions, countries, a drawn polygon or a rectangle by WGS84 coordinates. The global catalog contains 177 generalized Natural Earth geometries.

The selection connects map, calendar, comparison, explanation and export. It can be shared through a URL. That URL restores the configuration, but **it does not freeze a historical copy of the database**: results may change after new acquisitions.

Point inspection, camera controls, mobile layout and an informative fallback if WebGL does not start were added. Cesium ion is not required. The background has a local reference; tiles that are not cached need a connection.

Files: [App.tsx](../web/src/App.tsx), [Globe.tsx](../web/src/Globe.tsx), [style.css](../web/src/style.css).

### Calendar

The matrix of years and months lets you explore the series, select periods and review their historical reference. The color uses a logarithmic scale stated in the interface; the numbers keep their original values. On mobile, the months of each year expand.

Partial and unavailable periods have visible states. The seasonal profile accompanies the analysis and can be downloaded as SVG.

File: [Calendar.tsx](../web/src/Calendar.tsx).

### Visual lab and expedition

The comparator places MODIS Aqua and a selected VIIRS in the same scene, with a common camera and a slider. MODIS uses squares; VIIRS, circles. The slider works with the keyboard.

The comparison shares area and month; **it does not guarantee simultaneous overpasses or match pixels of the same observation**. Its differences cannot be attributed directly to real changes in fire.

Below it is the substitution experiment: an estimate, the Aqua reference that can be revealed and its error. This experiment uses a separate Peruvian case; it does not apply the model automatically to the country selected on the globe.

The expedition guides a three-step presentation: explore the problem, compare observers and reveal the experiment's evidence.

Files: [App.tsx](../web/src/App.tsx), [Experiment.tsx](../web/src/Experiment.tsx).

### Sources, evidence and downloads

The Sources panel shows the inventory, FIRMS availability, acquisition jobs and CSV import. The monthly download shows progress and keeps the loaded windows.

Five outputs were implemented: monthly series CSV, detections CSV, JSON manifest, TXT report and SVG figure. Analyses identify the selection, the data revision and the software revision. If the data or code change, the API refuses to use an outdated analysis to export or ask, and asks for it to be regenerated.

The manifest includes the catalog of loaded batches. It is file-level and database-revision provenance; it must not be read as a minimal list of all and only the files that contributed rows to the result.

Files: [DataPanel.tsx](../web/src/DataPanel.tsx), [Dialog.tsx](../web/src/Dialog.tsx), [nina/main.py](../nina/main.py).

## 6. What AI exists and what it does

### Trained statistical model

A regularized Poisson regression was implemented that estimates monthly counts relative to Aqua from the VIIRS count and seasonal terms. It is compared against a simpler method: multiplying VIIRS by a factor learned in training.

| Part | Data used |
|---|---|
| Training | 2018–2022, excluding the held-out regions |
| Regularization selection | Year 2023, excluding the held-out regions |
| Temporal test | 2024–2025 |
| Additional geographic check | Subset of regions held out through a deterministic rule |

There are saved models for VIIRS S-NPP and NOAA-20. There is no trained NOAA-21 model in this delivery.

| Input instrument | Model MAE | Simple factor MAE | Test pairs |
|---|---:|---:|---:|
| VIIRS S-NPP | 11.067 | 12.396 | 587 |
| VIIRS NOAA-20 | 10.907 | 12.709 | 597 |

MAE is the mean absolute error in detections per region/month against the Aqua archive. A lower value indicates a better fit on this test set; **it is not an accuracy percentage and does not demonstrate global validity**.

There is a relevant methodological limitation: training starts from months with a positive VIIRS count. If no Aqua count appears in that group, an archive zero is used; it is not verified that Aqua had a valid opportunity without detection. The visible experiment, for its part, only shows pairs where both counts appear. Its per-case error does not have to match the global benchmark metric.

L2 masks and geolocation, valid opportunities, cloud and geometry control and evaluated intervals are missing. The model does not yet rebuild a fire series free of those biases.

Code and results: [nina/science.py](../nina/science.py), [benchmark.json](../data/models/benchmark.json).

### Contextual assistant

The current assistant uses **rules and deterministic answers backed by the analysis**. It can explain the period, the instrument differences and the availability, and prepare a report. It presents the facts that support the answer and adapts the guidance to land management, research or communication.

There is an optional adapter to an LLM provider, but **it was not configured** when this delivery was reviewed. If enabled, the current design lets it contribute a guidance sentence; the figures still come from the server. It is not an agent that runs free geospatial queries or a full document RAG system.

Code: [nina/assistant.py](../nina/assistant.py), [Dialog.tsx](../web/src/Dialog.tsx).

## 7. Architecture actually implemented

| Component | Technology | Responsibility |
|---|---|---|
| Interface | React, TypeScript and Vite | Selection, navigation, calendar, panels and SVG export |
| Spatial visualization | CesiumJS | Globe, 2D, points, geometries and comparison |
| API | FastAPI and Uvicorn | Analyses, acquisitions, evidence, exports and assistant |
| Analytical database | DuckDB | Observation queries and local persistence |
| Spatial processing | Shapely | Validation, territorial assignment and clipping by geometry |
| Model computation | NumPy and SciPy | Poisson fit and evaluation against the simple method |
| Acquisition | HTTPX and the system trust store | Access to FIRMS and NASA GIBS |
| Jobs | Two workers inside the Python process | Background download, import and training |
| Files | Local disk, CSV, JSON and Parquet | Originals, provenance, model and analytical copy |

The browser queries the local API; the API queries DuckDB and reaches NASA when an acquisition or an uncached tile is requested. FIRMS is not called to recompute each calendar click over already loaded data.

The database protects reads and writes with a process lock to avoid mixing revisions during analyses and exports. This solution requires **a single server process** for the current local use. Job states are saved; on restart, a pending job is marked as interrupted and must be run again. There is no distributed queue with automatic resumption.

PostgreSQL/PostGIS, S3 storage, managed queues, multi-user authentication and cloud infrastructure are not deployed. Docker has a configuration, but no engine run that has not been verified is claimed.

### Main routes

| Route | Function |
|---|---|
| `GET /api/health` | Version and presence of configurations, without revealing keys |
| `GET /api/status` | Inventory and loaded observations |
| `GET /api/catalog` | Availability queried from FIRMS |
| `GET /api/places` and `/api/regions` | Reference geometries |
| `POST /api/analyses` | Compute and record an analysis |
| `GET /api/analyses/{id}/points` | Observed points and sampling metadata |
| `GET /api/analyses/{id}/comparison` | Two instruments for the same selection |
| `GET /api/analyses/{id}/evidence` | Selection, revisions and provenance |
| `GET /api/analyses/{id}/exports/{kind}` | Series, observations, manifest or report |
| `POST /api/acquisitions` and `/api/acquisitions/month` | Load recent windows or a month |
| `POST /api/import` | Import a FIRMS CSV with its scope |
| `GET /api/jobs` | Check job status |
| `GET /api/experiments/substitution` | Get held-out pairs and estimates |
| `GET /api/models` and `POST /api/models/train` | Query or train the exploratory model |
| `POST /api/assistant` | Explain an existing analysis |

The live contract can be checked at `http://127.0.0.1:8000/docs` and `http://127.0.0.1:8000/openapi.json`.

## 8. What was verified

Delivery 0.2 records the following checks; not all of them were re-run for this documentation-only change:

- TypeScript/Vite production build.
- 23 backend tests on analysis, import, scopes, revisions, availability, provenance and assistant.
- 20 automated browser checks: navigation, comparison, keyboard, mobile, experiment, shared link and five downloads, among others.
- Real monthly download started from the interface for Australia, September 2025, completed in six windows.
- Hash verification of the 57 files and row matching of the Parquet copy with the database.
- Visual review of the main views and the mobile layout.

While preparing this document the code, the delivery reports and the local `/api/health` and `/api/status` responses were reviewed again: version `0.2.0`, 2,108,030 observations and external LLM not configured.

References: [backend tests](../tests/test_nina.py), [delivery status](STATUS_V2.md), [data report](../data/release-v0.2.json). Browser reports and screenshots are in `.nina-qa/`, a local directory excluded from version control.

These checks verify software behavior and traceability. They do not replace an independent scientific validation or tests with real users.

## 9. What is missing to complete the scientific proposal

| Pending work | Why it is needed |
|---|---|
| Download and align L2 mask and geolocation products | Know where and when there was an opportunity to observe |
| Rebuild valid opportunities and absences | Separate lack of observation from absence of detection |
| Design and evaluate the harmonization per domain | Estimate instrument differences with appropriate controls |
| Evaluate uncertainty and geographic transfer | Publish where the method works and where it must abstain |
| Extend historical cases outside Peru | Evaluate generalization; the global viewer does not prove it by itself |
| Evaluate tasks with stakeholders | Check understanding and usefulness for real decisions |
| Prepare multi-user deployment and operation | Let the local solution operate as a shared service |

The next scientific step is to build the observation support and evaluate the method on it. Adding more points to the globe, by itself, does not meet that need.

## 10. How to review the delivery

Open `http://127.0.0.1:8000`. If the server is stopped, from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn nina.main:app --host 127.0.0.1 --port 8000
```

A concrete walkthrough to check the work:

1. Choose **Peru**, **MODIS Aqua**, **September 2025** and review atlas and calendar.
2. Open **Lab** and move the comparator; note that the sources keep separate counts.
3. Review the Peruvian experiment, reveal Aqua and check the error and the method.
4. Open the explanation and compare its figures with the facts shown.
5. Export observations and manifest to review records and provenance.
6. Select **Australia**, **MODIS Aqua**, **September 2025**: the loaded set contains 12,934 detections for that geometry.

More information: [startup and usage](../README.md), [sources](DATA_SOURCES.md), [status 0.2](STATUS_V2.md) and [product direction](../design/PRODUCT_DIRECTION.md).

This document uses tables and a sequence of steps. It does not include diagrams because Excalidraw MCP was not available in the session where it was written.
