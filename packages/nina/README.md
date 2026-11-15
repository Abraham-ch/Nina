# NINA harmonization pipeline

Offline package that turns NASA FIRMS active-fire detections from MODIS (Terra, Aqua) and VIIRS (S-NPP, NOAA-20) into
one comparable record: VIIRS-equivalent active cell-days on an H3 resolution-7 grid. The web server does not import
this package; it reads the Parquet product written here (see [ADR 0004](../../docs/adr/0004-offline-harmonization-pipeline.md)).

Method and gates: [ADR 0002](../../docs/adr/0002-archive-harmonization.md),
[ADR 0003](../../docs/adr/0003-static-source-priors.md). Current results and limits:
[docs/BACKEND_STATUS.md](../../docs/BACKEND_STATUS.md).

## Run

Run every command **from this folder** (`packages/nina/`). From the repository root, `python -m nina…` would load the
server package of the same name.

```powershell
cd packages/nina
uv sync
uv run python -m pytest -q tests

# Select (and, with --download, fetch) the yearly FIRMS archives and auxiliary layers
uv run python -m nina.io.acquire --workspace ../..
uv run python -m nina.io.acquire --workspace ../.. --download

# Normalize, deduplicate, apply QA and build cell-day activity
uv run python -u -m nina.io.harmonization --workspace ../..

# Train the coefficients, run leave-one-year-out validation and evaluate the gates
uv run python -u -m nina.io.model --workspace ../..

# Acceptance report, then the product (use --review for a private draft in source/review/)
uv run python -m nina.io.acceptance --workspace ../..
uv run python -m nina.io.product --workspace ../.. --review
```

`nina.io.model` and `nina.io.acceptance` exit with a non-zero code when a gate fails. That is deliberate.

Context layers for the territorial report (outputs in `source/context/`, see `docs/TERRITORIAL_REPORT.md`):

```powershell
uv run python -m nina.io.territory --workspace ../..          # districts, INDECI, fire events (~20 s)
uv run python -m nina.io.forest_loss --workspace ../.. --download   # Hansen tiles 1.4 GB, ~2 min
uv run python -m nina.io.climate --workspace ../.. --download       # NASA POWER, ~16 min first time
uv run python -m nina.io.territory --workspace ../.. --countries Peru Brazil Australia Indonesia "United States of America"  # events, ~10 min
uv run python -m nina.io.registries --workspace ../.. usa_nifc australia indonesia_bnpb brazil_ibama_roi  # needs source/downloads/validation/
uv run python -m nina.io.context_validation --workspace ../.. --part events-peru   # INDECI, ~3 min
uv run python -m nina.io.context_validation --workspace ../.. --part events-registry --country "United States of America" --registry usa_nifc --label "NIFC/WFIGS wildfire incidents"
uv run python -m nina.io.context_validation --workspace ../.. --part forest        # Geobosques
uv run python -m nina.io.context_validation --workspace ../.. --part climate       # CHIRPS (network)
```

## Layout

| Path | Role |
|---|---|
| `src/nina/calibration.py` | Coefficients (ratio of totals by country × biome × month × sampling regime) and validation metrics |
| `src/nina/coverage.py` | Sensor availability and sampling regimes |
| `src/nina/io/acquire.py`, `catalog.py` | Selection, download and hashing of inputs |
| `src/nina/io/harmonization.py` | Normalization, QA, deduplication, standard-over-NRT precedence, cell-day build |
| `src/nina/io/static_sources.py`, `geography.py` | Static-source mask, countries and biomes |
| `src/nina/io/model.py` | Training, leave-one-year-out validation, gates |
| `src/nina/io/product.py`, `acceptance.py` | Served product and acceptance report |
| `src/nina/io/territory.py` | Context layers for the territorial report: Peruvian districts (UBIGEO → H3 cells), INDECI forest-fire emergencies, fire events |
| `src/nina/io/forest_loss.py` | Tree-cover loss per H3 cell and year from Hansen/UMD GFC (Peru) |
| `src/nina/io/climate.py` | Monthly climate anomalies per Peruvian department from NASA POWER |
| `src/nina/io/registries.py` | Registered fire incidents of USA, Australia, Indonesia and Brazil normalised to one table per country |
| `src/nina/io/context_validation.py` | Validation of fire events, forest loss and climate against independent records |
| `src/nina/io/xlsx.py` | Minimal .xlsx reader (Geobosques tables) |

Inputs and outputs live in the repository's `source/` folder, which is not committed.
