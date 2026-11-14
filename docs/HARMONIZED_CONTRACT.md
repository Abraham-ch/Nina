# NINA · Contract for integrating the harmonized calendar

Read the [delivery status and its real results](BACKEND_STATUS.md) before presenting the draft. The harmonization has not
yet passed its scientific gates.

The local application runs with `start-nina.ps1` from the repository root. The server is `nina/main.py`, and the
harmonized-product routes are in `nina/harmonized.py`.

Observations remain at `/api/analyses`. The harmonized product uses `/api/harmonized/…`. A harmonized selection has no
sensor: sensor choice and calibration happen before the product is served.

## Check availability

`GET /api/harmonization`

| Status | Meaning and interface behaviour |
|---|---|
| `preparing` | Inputs are still being built. |
| `candidate_under_validation` | A candidate exists; it cannot yet be queried as an approved product. |
| `candidate_failed_validation` | One or more gates failed. Show the status and let the user keep exploring the original observations. |
| `validated_pending_acceptance` | The numeric gates passed; the acceptance evidence is incomplete. |
| `published` with `available=true` | A harmonized analysis can be created. |
| `experimental_candidate` | Local draft: `scientifically_validated=false`. Querying it is enabled explicitly for the demo through local configuration. |

`gates` holds the boolean results for the static mask, Terra only, Terra+Aqua and the NOAA-20 bridge. The full evaluation
is in `source/reports/validation_<version>.json`. The `source/` data are local and excluded from Git.

A POST without a published product returns **409** with `detail.message` and `detail.readiness`. Do not replace that error
with figures from another product.

The local demo can serve the draft when `NINA_EXPERIMENTAL_HARMONIZATION=true`. That option keeps every failed gate:
`validation_status=experimental` appears in the analysis, map and downloads. The approved scientific dataset keeps its own
path and lock. `.env.example` keeps the draft disabled.

## Create an analysis

`POST /api/harmonized/analyses`

```json
{
  "country": "Peru",
  "year_start": 2001,
  "year_end": 2025,
  "selected_year": 2025,
  "selected_month": 9,
  "geometry": null
}
```

`country` accepts `world` or a name from `/api/places` (for example `Brazil`, `Australia`, `Indonesia`,
`United States of America`, `Peru`). `geometry`, when used, is a GeoJSON Polygon/MultiPolygon in WGS84. H3 cell centres
inside the polygon are selected, including its edges and respecting holes. The national reference boundaries are
generalized; they are not official boundaries for local decisions.

The response contains `id`, `dataset_id`, `method_version`, `selection`, `unit`, `months`, `selected`, references and
limits. The Pydantic models generate the contract in `openapi.json`; TypeScript types are generated in `openapi.d.ts`.

Check `scientifically_validated` and `validation_status` before labelling the result. A monthly `status=complete` refers to
archive support; it does not turn an experimental draft into a scientifically approved product.

| Monthly field | How to read it |
|---|---|
| `value` | Comparable activity, or `null` when support or validation is missing. |
| `observed_activity` | Sum of the available equivalent activity, even when the requested scope is incomplete. Do not present it as a global total when `value=null`. |
| `unit` | `equivalent_VIIRS_active_cell_days`. Not individual fires or hectares. |
| `status` | `complete`, `provisional`, `partial_archive`, `incomplete_coverage`, `unvalidated_domain`, `not_available`. |
| `data_gap` | No valid support in that month. Show missing data. |
| `partial_coverage` | Regions/days are missing, or only the dates with detections in the archive are known. |
| `is_provisional` | NRT observations are involved. |
| `expected_region_days`, `valid_region_days` | Archive support by region and day; not a cloud-cover measurement. |
| `unvalidated_cell_days` | Cell-days whose adjustment has no accepted validation. They prevent a comparable total. |
| `eligible_for_climatology` | The month can be used as a historical reference. |
| `historical_median`, `historical_n`, `anomaly_percent` | Descriptive comparison with the same month in at least five earlier eligible years. |

A `null` is shown as missing data. A zero is only an archive zero under its documented support. The year 2000 is partial
and does not enter the climatology. Recent global archives do not by themselves certify that each month is complete;
outside the five historical countries, the multi-year comparison stays unavailable.

## Map, evidence and exports

| Method and route | Result |
|---|---|
| `GET /api/harmonized/analyses/{id}` | Retrieves the analysis for a specific version. |
| `GET /api/harmonized/analyses/{id}/points?limit=5000` | GeoJSON for the selected month: H3 centres, activity, total and displayed sample. Up to 10,000 points. |
| `GET /api/harmonized/analyses/{id}/exports/series` | Monthly CSV with unit, version, citation and legal notice. |
| `GET /api/harmonized/analyses/{id}/exports/manifest` | JSON with the analysis, selection, limits and references. |
| `GET /api/harmonized/analyses/{id}/exports/package` | ZIP with `series.csv`, every cell/day row of the selected month in `cells.csv`, `manifest.json` and a readme. |

Harmonized-product points are **cell centres**, not new fire locations. A weight can be fractional or larger than one: it
is adjusted equivalent activity, not a probability. Downloads are not limited to the map sample. The daily CSV carries
`sampling_bias_warning=true`; daily anomalies are not offered.

`cells.csv` includes `latitude`, `longitude` and `representation=H3_cell_center` so the aggregates open in a GIS. The
GeoJSON includes `calibration_validated` and `observed_cell_days` per cell; an unvalidated estimate must keep its status
when displayed.

If the dataset changes, an earlier analysis returns **409** and must be regenerated. If a published file fails its hash
check, the API returns **503**. Always keep `dataset_id` to tie calendar, map and download together.

## Evidence-based assistant

`POST /api/harmonized/assistant`

```json
{"analysis_id":"ID_RETURNED_BY_THE_POST","question":"How does this month compare with other years?"}
```

Returns `answer`, `facts`, `references`, `analysis_id` and `dataset_id`. It answers about comparisons, archive quality and
what the harmonization means. It is a deterministic, evidence-based engine; **it does not use an external LLM**. Do not
present it as a generative model or a fire prediction system. The observations MVP keeps its optional LLM adapter,
configurable through `.env`.

## Prepare the data

The scientific processing is an independent package in `packages/nina/` with its own uv environment (Python 3.12); the
server uses the root `.venv` (Python 3.14). Run the commands **from `packages/nina/`**: from the root, `python -m nina…`
would load the server package ([ADR 0004](adr/0004-offline-harmonization-pipeline.md)).

```powershell
cd packages/nina
uv sync
uv run python -m nina.io.acquire --workspace ../..
# Only on an installation that needs to download the selected originals:
uv run python -m nina.io.acquire --workspace ../.. --download
uv run python -u -m nina.io.harmonization --workspace ../..
uv run python -u -m nina.io.model --workspace ../..
```

Acquisition selects five countries, MODIS 2000–2025, S-NPP from 2012 and NOAA-20 from 2018, as available in the NASA
index. It checks sizes and SHA-256 hashes and reuses originals. The team's global data enter through the ingestion
scripts in `scripts/` and their observed Parquet; they are not redistributed in Git.

Training writes its reports even when a gate fails, and exits non-zero. Publication is a separate step:

```powershell
uv run python -m nina.io.product --workspace ../..
```

It also requires the acceptance report for the same inputs, with all mandatory checks passed. Do not edit `current.json`,
`publishable` or the thresholds to enable the product by hand.

To build a private draft, without passing the gates or enabling queries, use `nina.io.product --workspace ../.. --review`.
It goes to `source/review/`, separate from `source/harmonized/`. Regenerate the acceptance report with
`uv run python -m nina.io.acceptance --workspace ../..`; it exits non-zero when the candidate is not publishable.
