# NINA 0.2 · Global atlas and visual lab

Historical state of delivery 0.2. The later global ingestion is documented in [GLOBAL_STATUS.md](GLOBAL_STATUS.md).

[Startup and usage](../README.md). This delivery implements the agreed visual direction and extends acquisition to the whole world. The previous version remains documented in [STATUS_V1.md](STATUS_V1.md).

## Available

- CesiumJS 3D/2D viewer with real NASA GIBS imagery as tiles with a local cache; a global reference image is available offline. No Cesium ion account or paid map service.
- Global selection, 177 Natural Earth country geometries, Peru and its 26 divisions, drawn polygons and WGS84 coordinates. Global geometries have six decimals and identified topological repairs; they are generalized reference cartography.
- Territory and period shared across map, calendar, comparison and explanation; reproducible configuration link.
- MODIS Aqua/VIIRS comparator with real marker splits, a single camera and accessible controls. Square shape for MODIS, circular for VIIRS. Their raw counts are not mixed.
- Monthly calendar, descriptive comparison with the eligible median and seasonal profile; on mobile, collapsible years with readable months.
- Interactive experiment on held-out Peruvian counts: estimate, revealable Aqua reference, absolute error and method. Temporal split and geographic hold-out identified.
- Contextual assistant with verifiable facts, evidence and guidance by role. The local engine works; the LLM provider is optional and not configured. The lab calibration does use a trained machine learning model.
- Three-step guided expedition, analysis record and five real downloads: CSV series, CSV observations, JSON manifest, TXT report and SVG figure.
- FIRMS catalog queried with a MAP_KEY; recent global snapshot and one-month download per area in windows of up to five days. Background jobs with progress and persistence.
- Global or per-area import; standard/provisional revisions reconciled within their scope, without deleting data from other territories. Atomic reads during local ingestion.

## Real data loaded

| Set | Window | Files | CSV, bytes | New rows |
|---|---|---:|---:|---:|
| Peruvian archive | 2000–2025 depending on product | 48 | 163,067,831 | 2,034,899 |
| World: MODIS, NOAA-20, NOAA-21 | 14 Nov 2026, NRT | 3 | 4,116,918 | 49,410 |
| Australian rectangle: MODIS SP | September 2025 | 6 | 1,912,098 | 23,721 |
| Total loaded | Identified windows | 57 | 169,096,847 | 2,108,030 |

The exact Australia query with the Natural Earth geometry contains **12,934 Aqua detections** in September 2025. The downloaded rectangle total also contains Terra and points outside that geometry; they are kept and filtered at analysis time. The download was started from the interface and completed its six five-day windows.

## Verification

- TypeScript/Vite production build.
- 23 backend tests: analysis, provenance, revisions, scopes, coverage, import and role-based answers. Fixtures isolated from the real database.
- 20 automated browser checks across the main flow and additional interactions, plus a real monthly acquisition outside Peru. They include five downloads, restored link, keyboard, 2D/3D, area form, expedition and mobile.
- Visual review of atlas, calendar, comparison, experiment, assistant and Australia. Screenshots in `.nina-qa/nina-v2-*.png`.
- SHA-256 verification of the loaded files and matching of the Parquet snapshot through `scripts/verify_v2.py --refresh-parquet` with the service stopped; result in `data/release-v0.2.json`.

NASA credentials stay exclusively in the backend and `.env`; they are not included in the client, links or manifest.

## Material limits

1. The full global history is not downloaded. Selective acquisition works and the calendar represents its effective windows. The current-day snapshot is provisional and does not equal a full month.
2. Scientific harmonization with observation opportunities, L2 masks, exposure and geometry is still pending. The Peruvian model is exploratory and is not extrapolated to other countries. No coverage percentages or intervals are fabricated.
3. A pixel count is not equivalent to individual fires, burned area, cause, forecast or operational recommendation.
4. The calendar uses UTC. Natural Earth 110m countries and geoBoundaries divisions are geometries of their respective sets, not a certification of current official boundaries.
5. A local FastAPI/DuckDB process and a two-worker queue are kept. Partitioned storage, managed services and cloud deployment are architecture evolution, not deployed infrastructure.
6. The globe requires WebGL; the calendar and the coordinate query remain available if the viewer does not start. Tiles require a connection and the local reference image avoids an empty background.
7. Docker keeps its configuration, without claiming an engine or deployment test that has not been done. Stakeholder evaluation and independent scientific review remain pending.

## Next scientific work

Obtain L2 masks and geolocation, rebuild valid opportunities and zeros, evaluate biases and intervals per domain and publish where the harmonization has support. The design already connects selection, evidence and abstention so that result can be added without hiding its limits.
