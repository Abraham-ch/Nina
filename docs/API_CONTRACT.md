# API and database contract

> Location in the repo: `docs/API_CONTRACT.md`. Contract version: **v0.2.0**.
>
> **Status: target design of the harmonized version, NOT implemented.** The current API is the MVP one
> (`nina/main.py`, `/api/*` routes), described in `openapi.json` and in AGENTS §12. This document sets where it
> evolves. Where it assumes technologies the MVP does not use, the implementation follows the MVP unless an ADR says otherwise:
>
> | This document | MVP implementation |
> |---|---|
> | `serving` schema in PostGIS, SQL migrations, Alembic | DuckDB tables in `nina/store.py` (`data/nina.duckdb`) |
> | Martin tiles (`serving.v_hotspots_tiles`) | `GET /api/analyses/{id}/points` + CesiumJS |
> | Redis cache | Analyses persisted in the `analyses` table |
> | `nina.stats` | `nina/analytics.py` (and `nina/science.py` for calibration) |
> | Seed `packages/schemas/db/seed/` | Synthetic databases created by `tests/` |

> This document defines the two boundaries between teams:
>
> 1. **Processing → API**: tables of the `serving` schema (Part B; today, DuckDB tables in `nina/store.py`).
> 2. **API → Web**: REST endpoints `/api/v1` (Part A).
>
> **Source of truth in code:**
> - API: routes in `nina/main.py` and models in `nina/analytics.py` → `openapi.json` (root), generated with
>   `scripts/export_openapi.py` (not edited by hand). The web replicates the types in `web/src/types.ts`.
> - Database: schema in `nina/store.py`.
> - Legal texts: `docs/reference/firms_legal.json` (reference) and the interface (`web/src/`).
>
> This document and those files must match. If this document and AGENTS §12 differ, **this contract prevails**.
> Any change follows the process in `WORK_PLAN.md` §6.

---

## Part A · REST API

### A.1 General conventions

| Topic | Rule |
|---|---|
| Base | `/api/v1` |
| Format | JSON (UTF-8). Dates `YYYY-MM-DD`; instants ISO-8601 in UTC (`2025-11-05T00:00:00Z`) |
| Names | `snake_case` in JSON and in parameters |
| Errors | `application/problem+json` (RFC 9457) with an extra `code` field (§A.5) |
| Response headers | `X-Harmonization-Version`, `ETag`, `Cache-Control: public, max-age=3600` (provisional data use `max-age=600`) |
| Warnings | Non-blocking warnings go in `warnings: [{ "code": "...", "message": "..." }]` inside the body |
| Source sensor | **Not exposed** in the analysis endpoints. Only `/meta` and the export with `include_source=true` |
| Authentication | None in v1 (public data). Per-IP rate limit at the *reverse proxy* |

### A.2 Common query parameters (`QueryParams`)

Used by `/calendar`, `/timeseries`, `/ranking`, `/hotspots` and `/export/*`.

| Parameter | Type | Required | Default | Rule |
|---|---|---|---|---|
| `region_id` | string | one of the three | — | Id from `/regions` (e.g. `PER.15_1`) |
| `bbox` | string `W,S,E,N` | one of the three | — | Decimal degrees, WGS84 |
| `geometry_id` | string (uuid) | one of the three | — | Returned by `POST /geometries` (valid 24 h) |
| `start` | date | yes | — | ≥ `2000-11-01` |
| `end` | date | yes | — | ≥ `start`, ≤ latest available date |
| `tz` | IANA string | no | `UTC` | Grouping by local date (e.g. `America/Lima`) |
| `min_confidence` | `nominal` \| `high` | no | `nominal` | `low` is never available |
| `daynight` | `all` \| `D` \| `N` | no | `all` | |

**Exactly one** of `region_id`, `bbox` or `geometry_id` is passed. Otherwise the response is `422 INVALID_REGION_SPEC`.

### A.3 Endpoints

#### `GET /health`

Used for *liveness* and *readiness*.

```json
{ "status": "ok", "db": "ok", "cache": "ok", "harmonization_version": "0.3.0" }
```

#### `GET /meta`

Returns the dataset metadata. The web uses it in the footer, in "Dataset details" and to bound the selectable dates.

```json
{
  "harmonization_version": "0.3.0",
  "generated_at": "2026-11-10T06:00:00Z",
  "date_min": "2000-11-01",
  "date_max": "2026-11-13",
  "provisional_from": "2026-06-30",
  "climatology_years": [2001, 2025],
  "sensors": [
    { "sensor": "modis_terra", "first_date": "2000-11-01", "last_date": "2026-11-13", "status": "active" },
    { "sensor": "viirs_snpp", "first_date": "2012-01-20", "last_date": "2026-11-02", "status": "end_of_mission" }
  ],
  "known_gaps": [ { "start": "2020-08-16", "end": "2020-09-02", "scope": "aqua", "reason": "known_outage" } ],
  "citation": { "text": "...", "dois": ["10.5067/FIRMS/MODIS/MCD14ML", "..."] },
  "disclaimer": { "es": "...", "en": "..." }
}
```

`citation` and `disclaimer` are read from `docs/reference/firms_legal.json` (not from the database), as in the web.

#### `GET /regions`

Searches administrative regions.

| Parameter | Type | Default |
|---|---|---|
| `q` | string (accent- and case-insensitive search) | — |
| `country` | ISO3 | — |
| `level` | 0–3 | — |
| `limit` | 1–100 | 20 |

```json
{
  "items": [
    { "region_id": "PER.15_1", "name": "Lima", "level": 1, "country": "PER",
      "parent_id": "PER", "bbox": [-77.9, -13.3, -75.5, -10.3], "area_km2": 34802 }
  ]
}
```

#### `GET /regions/{region_id}`

Returns one region with its simplified geometry.

| Parameter | Type | Default |
|---|---|---|
| `simplify` | metres | `500` |

Responds with a GeoJSON `Feature` whose `properties` are the same as an item of `/regions`. If it does not exist: `404 REGION_NOT_FOUND`.

#### `POST /geometries`

Uploads a drawn area or a user file and returns a reusable `geometry_id`.

- **Input:** `application/geo+json` (a Feature or a FeatureCollection of polygons) or `multipart/form-data` with `file` (a Shapefile `.zip` or a `.geojson`, at most 10 MB).
- **Process:** reprojects to EPSG:4326, fixes the geometry (`make_valid`) and merges all polygons into one multipolygon.

```json
{ "geometry_id": "8f0c…", "area_km2": 1532.4, "bbox": [-76.1, -12.3, -75.7, -11.9],
  "expires_at": "2026-11-15T09:00:00Z", "warnings": [] }
```

Errors: `422 INVALID_GEOMETRY`, `413 FILE_TOO_LARGE`, `422 AREA_TOO_LARGE` (if it exceeds `MAX_AREA_KM2`).

#### `GET /calendar`

Year × month matrix of the region. It is the main view of the app.

| Extra parameter | Type | Default |
|---|---|---|
| `metric` | `hotspots` \| `active_cells` | `hotspots` |

```json
{
  "query": { "region_id": "PER.15_1", "start": "2001-01-01", "end": "2026-10-31", "tz": "UTC",
             "min_confidence": "nominal", "daynight": "all", "metric": "hotspots" },
  "harmonization_version": "0.3.0",
  "climatology_years": [2001, 2025],
  "scale": { "count_breaks": [0, 3, 10, 30, 100, 300], "anomaly_breaks": [-2, -1, -0.5, 0.5, 1, 2] },
  "cells": [
    { "year": 2024, "month": 9, "value": 412.6, "climatology_median": 180.0,
      "climatology_p10": 60.0, "climatology_p90": 350.0, "anomaly_z": 1.8, "percentile": 96,
      "rank_in_month": 2, "data_gap": false, "partial_coverage": false,
      "is_provisional": false, "low_observability": false }
  ],
  "warnings": []
}
```

Rules:

- `value` is `null` if `data_gap = true`. **Never** return 0 for a gap.
- Months partially outside `[start, end]` are included with `partial_period: true`.
- `anomaly_z` and `percentile` are computed against the climatology of the same month (`nina/analytics.py`).
- `rank_in_month` is the year's position among all years for that month (1 = the most active).

#### `GET /timeseries`

Time series with the climatological band.

| Extra parameter | Type | Default |
|---|---|---|
| `freq` | `day` \| `week` \| `month` | `month` |
| `metric` | `hotspots` \| `active_cells` | `hotspots` |
| `compare_years` | comma-separated list of years (max. 5) | — |

```json
{
  "query": { "...": "..." },
  "freq": "week",
  "points": [
    { "period_start": "2024-09-02", "value": 88.1, "climatology_median": 41.0,
      "climatology_p10": 9.0, "climatology_p90": 95.0,
      "data_gap": false, "is_provisional": false }
  ],
  "compare": [ { "year": 2023, "points": [ { "period_start": "2023-09-04", "value": 30.2 } ] } ],
  "warnings": [ { "code": "SAMPLING_BIAS", "message": "Aggregations shorter than 8 days have sampling bias." } ]
}
```

`freq=day` **always** includes the `SAMPLING_BIAS` warning and does **not** return the climatology fields (SAMP-01).

#### `GET /ranking`

Years sorted by activity.

| Extra parameter | Type | Default |
|---|---|---|
| `months` | list `1–12` (season; e.g. `7,8,9,10`) | all |
| `top` | 1–30 | 10 |

```json
{ "items": [ { "year": 2024, "value": 2310.4, "anomaly_z": 2.1, "excluded": false } ],
  "excluded_years": [ { "year": 2002, "reason": "partial_coverage" } ] }
```

#### `GET /hotspots`

Individual hotspots of the query, for the map and for inspection.

| Extra parameter | Type | Default |
|---|---|---|
| `limit` | 1–5000 | 1000 |
| `cursor` | opaque string | — |

The response is a GeoJSON `FeatureCollection` plus `next_cursor`. Each feature carries
`hotspot_id`, `acq_datetime_utc`, `frp_mw`, `confidence_class`, `daynight` and `is_provisional`.

To show many points, the web uses the **vector tiles** (§A.4), not this endpoint.

#### `GET /export/hotspots`

Download of the query's hotspots.

| Extra parameter | Type | Default |
|---|---|---|
| `format` | `csv` \| `zip` | `zip` |
| `include_source` | bool | `false` |

- `csv`: streamed `text/csv`, UTF-8 with BOM, with the columns of AGENTS §12.1.
- `zip`: includes `hotspots.csv` and `README.txt` (citation, DOI, warning, filters used and version).
- Limit: `EXPORT_MAX_ROWS` (default 1,000,000). If exceeded: `413 EXPORT_TOO_LARGE`, with the estimated count in `detail`.

#### `GET /export/calendar`

Downloads the `/calendar` matrix.

| Extra parameter | Type | Default |
|---|---|---|
| `format` | `csv` \| `zip` | `csv` |
| `metric` | `hotspots` \| `active_cells` | `hotspots` |

Columns: `year, month, value, climatology_median, climatology_p10, climatology_p90, anomaly_z, percentile, data_gap, partial_coverage, is_provisional`.

### A.4 Vector tiles (outside FastAPI)

| Resource | URL | Owner |
|---|---|---|
| Hotspots | `{VITE_TILES_URL}/serving.v_hotspots_tiles/{z}/{x}/{y}` (Martin) | API (configuration) + Processing (view) |

- Attributes: `hotspot_id`, `date` (integer `YYYYMMDD`), `frp_mw`, `confidence_class`.
- The web filters by date on the client with MapLibre expressions.

### A.5 Errors

```json
{ "type": "https://fire-calendar/errors/area-too-large", "title": "Area too large",
  "status": 422, "code": "AREA_TOO_LARGE", "detail": "The area (812,000 km²) exceeds the maximum (500,000 km²)." }
```

| `code` | HTTP | When |
|---|---|---|
| `INVALID_REGION_SPEC` | 422 | None, or more than one, of `region_id`, `bbox` and `geometry_id` |
| `REGION_NOT_FOUND` | 404 | Non-existent `region_id` |
| `GEOMETRY_EXPIRED` | 410 | Expired `geometry_id` |
| `INVALID_GEOMETRY` | 422 | Invalid geometry or file |
| `AREA_TOO_LARGE` | 422 | Area > `MAX_AREA_KM2` |
| `INVALID_DATE_RANGE` | 422 | `start > end`, or outside `[date_min, date_max]` |
| `INVALID_PARAMETER` | 422 | Another parameter out of domain |
| `FILE_TOO_LARGE` | 413 | Upload > 10 MB |
| `EXPORT_TOO_LARGE` | 413 | Export > `EXPORT_MAX_ROWS` |
| `INTERNAL_ERROR` | 500 | Unhandled error (logged with a `request_id`) |

**Warning** codes (`warnings`, not errors): `SAMPLING_BIAS`, `PROVISIONAL_DATA`, `PARTIAL_COVERAGE`, `DATA_GAPS`, `GEOMETRY_REPAIRED`.

### A.6 Expected performance (to review in Phase 4)

| Endpoint | Target p95 (region ≤ 50,000 km², 25 years) |
|---|---|
| `/calendar` (administrative region, precomputed) | < 300 ms |
| `/calendar` (free geometry) | < 2 s |
| `/timeseries?freq=week` | < 2 s |
| `/export/hotspots` (first byte) | < 1 s |

---

## Part B · Database contract (Processing → API)

**Ownership rules:**

- Processing owns the `serving` schema: it writes the DDL in `packages/schemas/db/serving.sql`, applies the migrations in
  `packages/schemas/db/migrations/NNN_*.sql` and loads the data.
- The API **only reads** from `serving`. The API's own objects, if needed, go in the `api` schema, with Alembic migrations
  in `apps/api/migrations`.

### B.1 `serving` tables and views

| Object | Grain | Main columns | Indexes |
|---|---|---|---|
| `serving.cell_day` | `h3_cell × date` | `h3_cell text`, `date date`, `hotspots_equiv real`, `active_equiv real`, `data_gap bool`, `partial_coverage bool`, `is_provisional bool`, `low_observability bool` | PK (`h3_cell`, `date`); BRIN (`date`) |
| `serving.cell_geom` | `h3_cell` | `h3_cell text PK`, `geom geometry(Polygon,4326)`, `centroid geometry(Point,4326)` | GIST (`geom`) |
| `serving.hotspots` | detection | `hotspot_id text PK`, `acq_datetime_utc timestamptz`, `acq_date date`, `geom geometry(Point,4326)`, `h3_cell text`, `frp_mw real`, `confidence_class text`, `daynight char(1)`, `quality_level text`, `is_provisional bool`, `instrument text`, `satellite text` | GIST (`geom`); BRIN (`acq_date`); btree (`h3_cell`, `acq_date`) |
| `serving.region` | administrative region | `region_id text PK`, `name text`, `name_norm text`, `level smallint`, `country char(3)`, `parent_id text`, `geom geometry(MultiPolygon,4326)`, `area_km2 real` | GIST (`geom`); trigram (`name_norm`) |
| `serving.region_cell` | `region_id × h3_cell` | `region_id`, `h3_cell`, `weight real` (fraction of the cell inside the region) | PK (`region_id`, `h3_cell`) |
| `serving.region_month` (materialized view) | `region_id × year × month × metric` | `value`, `data_gap_days`, `partial_days`, `provisional_days` | PK |
| `serving.global_day_status` | `date` | `data_gap bool`, `partial_coverage bool`, `is_provisional bool`, `sensors text[]` | PK (`date`) |
| `serving.dataset_meta` | 1 row | `harmonization_version`, `generated_at`, `date_min`, `date_max`, `provisional_from`, `climatology_start`, `climatology_end` | — |
| `serving.sensor_coverage` | `sensor` | `first_date`, `last_date`, `status` | — |
| `serving.known_gaps` | period | `start`, `end`, `scope`, `reason` | — |
| `serving.v_hotspots_tiles` | view | `hotspot_id`, `geom` (EPSG:3857), `date int`, `frp_mw`, `confidence_class` (only those that passed QA) | — |

### B.2 Guarantees provided by Processing

1. Loading is **atomic per version**: it writes to `serving_next` and swaps it with `serving` in a single transaction,
   so the API never sees half-written data.
2. `serving.dataset_meta.harmonization_version` changes on every publication. The API uses that value to invalidate the cache.
3. Values in `serving.cell_day` are already harmonized ("VIIRS equivalent") and QA-filtered.
4. `data_gap = true` implies `hotspots_equiv IS NULL`.
5. There is a small synthetic **seed** with the same DDL: `packages/schemas/db/seed/seed.sql.gz`. It covers a test region,
   2001–2025, and deliberately includes gaps, provisional months and partial coverage.

### B.3 Shared logic

The climatology, percentile, anomaly and ranking formulas live **only** in `nina/analytics.py` (target: a `nina/stats.py` module), as pure
functions without I/O. The API imports them; it does not reimplement them. Processing owns the module and the API reviews its changes.

| Function | Signature (summary) |
|---|---|
| `monthly_climatology(values_by_year_month, years) -> {month: (median, p10, p90)}` | Excludes months with a gap or partial coverage > 20 % |
| `anomaly(value, climatology) -> (z, percentile)` | Robust z: `(x - median) / (1.4826 · MAD)` |
| `rank_years(values_by_year, months) -> [(year, value, z, excluded)]` | |
| `count_breaks(values) -> list[float]` / `ANOMALY_BREAKS` | Color scale breaks used by the web |

---

## Contract history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-11-14 | Initial version |
| 0.1.1 | 2026-11-14 | Paths to the current project (`nina`, `apps/api/API_CONTRACT.md`); OpenAPI generated from `models.py` instead of a hand-written `openapi.yaml`; citation and warning from `packages/schemas/legal/` (removed from `serving.dataset_meta`) |
| 0.2.0 | 2026-11-14 | MVP integrated at the root: the document becomes a target design; equivalence table with the MVP's DuckDB/FastAPI; paths updated |
