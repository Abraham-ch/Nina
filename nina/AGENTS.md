# AGENTS.md · `nina/` — Roles A (processing) and B (API)

> Takes precedence over the root `AGENTS.md` for files in this folder. Full split of responsibilities in `WORK_PLAN.md` §2.
> `nina/` is a single package: **ownership is per file**.

## Who writes what

| File | Owner |
|---|---|
| `ingest.py`, `global_ingest.py`, `remote.py`, `science.py`, `store.py` | **A** (changes to `store.py` are reviewed by B) |
| `main.py`, `analytics.py`, `assistant.py`, `config.py`, `harmonized.py` | **B** (changes to `config.py` are reviewed by A) |

Outside `nina/`: A also writes `scripts/` (except `export_openapi.py`), `data/boundaries/`, `docs/reference/`,
`notebooks/`, `tests/test_global_ingest.py`. B also writes `openapi.json`, `scripts/export_openapi.py`, the rest of
`tests/`, dependencies, Docker, launchers and `.github/`. Neither A nor B writes `web/**`. If you need something from another
owner: `docs/requests/<role>-<slug>.md`.

## Package rules

- Sensor-specific logic (origin, normalization, SP/NRT precedence, Landsat exclusion) lives only in A's
  modules. `analytics.py` and `main.py` consume the database; they do not reinterpret the original files.
- DuckDB access only through `store.database()` / `atomic_read`. New columns: `ALTER TABLE … ADD COLUMN IF NOT EXISTS`
  in `initialize()`; never break existing databases.
- A single process writes the database: console imports use `--data-dir data/<staging>` or a stopped server.
- Routes only in `main.py`; logic in `analytics.py`. When routes or models change: `scripts/export_openapi.py` and notify C.
- Every discarded row is counted (`rejected`, `duplicates`, `excluded_files`).
- Gap ≠ partial ≠ zero in every result.
- Originals in `source/`: the team's static files at the root (input of `scripts/import_global.py`, global scope) and everything
  downloaded or uploaded in `config.RAW` (`source/downloads/`). Never store downloads at the root of `source/` or in `data/`.
  Derived files go in `config.DATA` (`data/`).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/export_openapi.py   # if the API changed; commit openapi.json
```

Commits: `feat(nina): …` (A), `feat(api): …` / `fix(api): …` (B) · Branches: `nina/<slug>`, `api/<slug>`.
