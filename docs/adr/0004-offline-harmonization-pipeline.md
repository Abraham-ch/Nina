# ADR 0004 — The harmonization pipeline is an offline package; the server only reads its output

Date: 2026-11-14 · Status: accepted

## Context

Two lines of work met in this repository:

- The application (`nina/` + `web/`) is a single project: Python 3.14 + pip, FastAPI, DuckDB, React. Its rules say that
  H3, uv and a `packages/` tree are only brought in with an ADR.
- The MODIS ↔ VIIRS harmonization (ADR 0002, ADR 0003) was built as a separate package, `packages/nina/`, with its own
  dependencies (H3, Polars, GeoPandas, PyArrow) and a Python 3.12 environment managed with uv.

The harmonization is the core of the challenge and has to ship with the application. Rewriting it inside the server
package would add heavy dependencies to the server and would mean re-validating code that already has tests and
validation reports.

## Decision

1. The pipeline stays in `packages/nina/` as a **self-contained, offline** project (`pyproject.toml`, `uv.lock`,
   `.python-version` = 3.12). It is the only place where H3 and uv are used. It is not imported by the server.
2. The server reads the pipeline's **precomputed Parquet product** through `nina/harmonized.py` (routes
   `/api/harmonization` and `/api/harmonized/*`). It needs only DuckDB and Shapely, which the server already uses.
   No calibration happens at query time.
3. Shared reference files have one home, `docs/reference/` (`known_gaps.yaml`, `sensor_lifecycle.yaml`,
   `qa_report.schema.json`, `firms_legal.json`), and the acceptance criteria live in `docs/ACCEPTANCE_CRITERIA.md`.
   The pipeline reads them from there.
4. Product files live under `source/` (`source/harmonized/` when published, `source/review/` for a draft), resolved
   through `nina.config.SOURCE`, so `NINA_SOURCE_DIR` applies to them as well.

## Consequences

- There are two Python packages named `nina`: the server (`nina/`) and the pipeline (`packages/nina/src/nina/`). They
  never run in the same process. Pipeline commands must be run **from `packages/nina/`**; from the repository root,
  `python -m nina…` resolves to the server package.
- The server works without the pipeline environment, and the pipeline works without the server.
- A machine that only has the Git repository has no harmonized product: the Parquet files (about 200 MB) must be
  generated with the pipeline or copied into `source/`.
- Renaming the pipeline package to remove the name clash is possible later; it was not done now to keep the validated
  code unchanged.
