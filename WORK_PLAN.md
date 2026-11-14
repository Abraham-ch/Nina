# Work plan · 3 people, 3 agents

> Location in the repo: `WORK_PLAN.md` (root). Global rules: `AGENTS.md`. Current API contract: `openapi.json`;
> target contract of the harmonized version: `docs/API_CONTRACT.md`. Detailed scientific tasks (N01–N18):
> `docs/IMPLEMENTATION_PLAN.md`.
>
> **Starting point:** the NINA 0.3 MVP already works (globe, calendar, comparison, exports, assistant, global
> archive 2025–2026). This plan splits its evolution towards validated harmonization among three people, without them stepping on each other.
>
> Three principles:
>
> 1. **Contracts first.** The boundaries are the DuckDB schema (`nina/store.py`) and the API (`openapi.json`).
> 2. **Each person owns their files.** Their agent only writes there.
> 3. **Each boundary has a double**, so nobody depends on the other having finished (§3).

---

## 1. Roles

| Role                     | Person   | Agent   | Packages (turbo filter)                 | Responsibility                                                                                                              |
| ------------------------ | -------- | ------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **A · Processing**       | _(name)_ | Agent A | `@fire/nina`                            | FIRMS ingestion, QA, harmonization, validation, loading into `serving`, seed, `nina.stats`; later `pipelines/` (NRT jobs)   |
| **B · API and platform** | _(name)_ | Agent B | `@fire/api`, `@fire/schemas`            | FastAPI, Pydantic models → `openapi.json`, cache, exports, tiles (Martin), Docker, CI/CD, deployment                        |
| **C · Web**              | _(name)_ | Agent C | `@fire/web`, `@fire/ui`, `@fire/config` | React app, `@fire/ui` (CalendarHeatmap, map, selectors), API mocks, accessibility, i18n                                     |

If a fourth person joins, it is worth splitting **A**: A1 · ingestion and QA (`ingest.py`, `global_ingest.py`, `remote.py`) and
A2 · science (`science.py`, notebooks, validation).

---

## 2. File ownership (what each agent may write)

`nina/` is a single package shared by A and B, so ownership is **per file**:

| Path                                                                                     | Owner            | Reviews                                    | Notes                                                                                                                     |
| ---------------------------------------------------------------------------------------- | ---------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `packages/nina/**`                                                                       | A                | B (only `src/nina/stats.py` and `config.py`) | Includes `known_gaps.yaml`, `sensor_lifecycle.yaml`, `ACCEPTANCE_CRITERIA.md`                                           |
| `pipelines/**` (from Phase 3)                                                            | A                | B                                          | Only orchestrates `nina` functions; added to the workspace (`pnpm-workspace.yaml`, `pyproject.toml`) in an `infra:` PR by B |
| `notebooks/**`                                                                           | A                | —                                          | Nothing here is imported by production                                                                                    |
| `source/**`                                                                              | each one, local  | —                                          | Gitignored. Never committed                                                                                               |
| `packages/schemas/json/**`                                                               | A                | B                                          | Input contract (AGENTS §6)                                                                                                |
| `packages/schemas/db/**` (`serving` DDL, migrations, seed)                               | A                | **B required**                             | A→B boundary                                                                                                              |
| `apps/api/**`                                                                            | B                | —                                          | `src/fire_api/models.py` is the B→C boundary: **C must review**                                                           |
| `apps/api/API_CONTRACT.md`                                                               | B                | **A and C required**                       | Document of both boundaries                                                                                               |
| `packages/schemas/openapi/openapi.json`, `packages/schemas/src/generated/**`             | **nobody by hand** | C                                        | Regenerated with `pnpm gen:types` in the same PR that changes the models                                                  |
| `packages/schemas/legal/**`                                                              | B                | C                                          | FIRMS citation and notices (a single place; API and web read them from here)                                              |
| `packages/schemas/package.json`, `tsconfig.json`, `src/index.ts`                         | B                | C                                          |                                                                                                                           |
| `infra/**`, `.github/**`                                                                 | B                | —                                          |                                                                                                                           |
| Root configuration (`package.json`, `turbo.json`, `pnpm-workspace.yaml`, `pyproject.toml`) | B              | A and C                                    | Small, announced changes                                                                                                  |
| `.env.example`                                                                           | per section      | B                                          | Each role adds variables **only in its section** (§2.1)                                                                   |
| `apps/web/**`                                                                            | C                | —                                          |                                                                                                                           |
| `packages/ui/**`                                                                         | C                | —                                          |                                                                                                                           |
| `packages/config/**` (TS/ESLint/Prettier)                                                | C                | B                                          | ruff/mypy live in the root `pyproject.toml` (B)                                                                           |
| `uv.lock`, `pnpm-lock.yaml`                                                              | **nobody by hand** | —                                        | On conflict: take the `main` version and regenerate with `uv lock` / `pnpm install`                                       |
| Root `AGENTS.md`, `WORK_PLAN.md`                                                         | everyone         | everyone (2 approvals)                     |                                                                                                                           |
| `docs/adr/**`                                                                            | whoever proposes | everyone                                   |                                                                                                                           |
| `docs/requests/**`                                                                       | anyone           | target role                                | Requests between areas (§7)                                                                                               |

These rules are enforced with `.github/CODEOWNERS` (pending: B creates it with the GitHub users) and with the
area `AGENTS.md` files: `nina/AGENTS.md` (A and B) and `web/AGENTS.md` (C).

### 2.1 Shared files without conflicts

- **`nina/main.py`**: B only. If A needs to expose something new, A publishes a function in its module and requests the route in
  `docs/requests/api-<slug>.md`.
- **`requirements.txt`**: one dependency per line, in alphabetical order; whoever adds it regenerates the lock in the same PR.
  On a lock conflict: take the one from `main` and regenerate it, never resolve it by hand.
- **`web/package-lock.json`**: same (`npm.cmd --prefix web install`).
- **`.env.example`**: each new variable with a one-line comment; reviewed by B.

---

## 3. Boundaries and their doubles

| Boundary | Contract                                                                                                                                  | Double to work without waiting                                                                                                                                                       | Who provides it                                                            | When            |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- | --------------- |
| A → B    | `packages/schemas/db/serving.sql` + API_CONTRACT Part B                                                                                   | **Synthetic seed** `packages/schemas/db/seed/seed.sql.gz` (one region, 2001–2025, with gaps, provisional data and partial coverage), generated by `packages/schemas/db/seed/make_seed.py` | A                                                                          | End of Phase 0  |
| A → B    | `nina.stats` (signatures, `packages/nina/src/nina/stats.py`)                                                                              | Simple initial implementation; the final formulas arrive in Phase 3                                                                                                                  | A                                                                          | End of Phase 0  |
| B → C    | Pydantic models (`apps/api/src/fire_api/models.py`) → `packages/schemas/openapi/openapi.json` + `@fire/schemas` types + API_CONTRACT Part A | **MSW mocks** (`apps/web/src/mocks/`) built from the `examples` B puts in the models                                                                                                 | B writes the models with `examples` and route _stubs_; C builds the mocks  | End of Phase 0  |
| B → C    | `serving.v_hotspots_tiles` tiles                                                                                                          | Static GeoJSON with the seed's hotspots                                                                                                                                              | A (view) + B (Martin)                                                      | Phase 2         |

**How each boundary is protected (CI, blocks the merge):**

- **Phases 0–2 (no tests):** `pnpm turbo run typecheck` is the safety net. Since the web compiles against the generated
  types, a change in B's models that breaks C fails CI in that same PR.
- **From Phase 3 (contract tests, block the merge):**
    - **A→B:** A's loader validates that `serving` matches `serving.sql`. API tests run against the seed.
    - **B→C:** the API is tested against `openapi.json` with Schemathesis. CI regenerates `openapi.json` and fails if it differs from the
      committed one. The web compiles with the generated types.

---

## 4. Phases and milestones

Estimated duration: **1 to 2 weeks** per phase. ✅ = already in `main`.

### Phase 0 · Integration and common base → **Milestone M0: "MVP at the root, clear contracts"**

| A · Processing                                                                     | B · API and platform                                                                             | C · Web                                                 |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| ✅ `nina` skeleton + `config.py` + `known_gaps.yaml` + `sensor_lifecycle.yaml`     | ✅ Monorepo skeleton (AGENTS §3.4), CI and docker-compose                                        | ✅ Vite + React skeleton                                |
| ✅ `packages/schemas/json/hotspot_input.schema.json`                               | ✅ Minimal `/api/v1/meta` · ✅ `packages/schemas/legal/firms.json`                               | ✅ `@fire/config` (tsconfig, ESLint, Prettier)          |
| `serving.sql` v0.1 (with B)                                                        | `models.py` v0.1 + _stubs_ of every endpoint returning its `examples`; `pnpm gen:types`          | Router + TanStack Query; MSW mocks from the `examples`  |
| Synthetic seed + `make_seed.py`                                                    | `/health` with the seed loaded; `.github/CODEOWNERS`                                             | Wireframes: selection, calendar, series, export         |
| `stats.py` signatures                                                              | _problem+json_ and warnings template                                                             | `features/` structure                                   |

**M0 is met when:** all three run `setup-nina.ps1` + `start-nina.ps1` from the root, CI is green and
`CODEOWNERS` applies the table in §2.

### Phase 1 · Complete data and QA (N03–N06, N17)

| A                                                                                     | B                                                   | C                                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------------- | --------------------------------------------------- |
| FIRMS ingestion from `source/`: JSON/CSV/SHP readers, origin detection (ING-01…06)    | `/meta`, `/regions`, `/regions/{id}` over the seed  | Map (MapLibre) + `RegionPicker` (search, drawing)   |
| Normalization and schema (SCH, TMP)                                                   | `POST /geometries` (GeoJSON/SHP, validation, Redis) | `DateRangePicker` bounded by `/meta`                |
| Confidence (CONF) + QA report in `source/reports/` (OUT-01…03)                        | Error middleware, headers, `ETag`                   | i18n `en`/`es`                                      |
| FIRMS API client (SRC-04, SRC-07)                                                     |                                                     | Footer with citation and warning (from `/meta`)     |

### Phase 2 · Harmonization science (N07–N11) → **Milestone M1: "calibration evaluated"**

| A                                                                     | B                                                 | C                                                                                     |
| --------------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Gaps (GAP-01…07) using `known_gaps.yaml` and `sensor_lifecycle.yaml`  | `/calendar` and `/timeseries` (using `nina.stats`) | `CalendarHeatmap` in `@fire/ui`: count/anomaly modes, gap, provisional, legend      |
| Static-source mask (TYPE)                                             | Redis cache, invalidation by version              | Time series with band and `SAMPLING_BIAS` warning                                     |
| H3 grid and `cell_day` (PIX)                                          | Tile view + Martin                                | Tile layer on the map                                                                 |

**M1 is met when:** a reproducible validation report exists and the decision (accept or not) is recorded in an ADR.

### Phase 3 · Harmonized product (N11–N15)

| A                                                                     | B                                                                          | C                                                                       |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| MODIS↔VIIRS calibration (HAR-01…05)                                   | `/ranking`, `/hotspots` (cursor)                                           | Year ranking, year comparison                                           |
| S-NPP↔NOAA-20 bridge (SRC-02)                                         | `/export/hotspots` and `/export/calendar` (_streaming_, zip with `README.txt`) | Download buttons, `EXPORT_TOO_LARGE` handling                        |
| Final `stats` formulas + leave-one-year-out validation                | Limits (`MAX_AREA_KM2`, `EXPORT_MAX_ROWS`)                                 | Error and empty states for every code in API_CONTRACT §A.5              |
| Fixtures (AGENTS §15) and required `nina` tests                       | Adds `test` to turbo/CI; Schemathesis and `openapi.json` comparison        | Component tests for `CalendarHeatmap`                                   |
| Creates `pipelines/` (`backfill`) and backfills the pilot region      | `infra:` PR that adds `pipelines` to the workspace                         |                                                                         |

### Phase 4 · Close-out (N16, N18) → **Milestone M2: "release"**

| A                                                               | B                                                                 | C                                                             |
| --------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------- |
| Atomic load into `serving` (B.2), `region_cell`, `region_month` | Query and index tuning against the p95 in API_CONTRACT §A.6       | Performance (many cells, _lazy loading_)                      |
| Scheduled `nrt_daily` and `sp_replace` jobs                     | Staging deployment, observability (logs, Sentry)                  | User tests: emergency managers (2 or 3 sessions)              |
| Complete acceptance report (ACCEPTANCE_CRITERIA)                | Basic load tests                                                  | Color scale and text adjustments                              |

### Phase 5 · Hardening → **Milestone M3: "release v1.0"**

| A                                                             | B                                            | C                                                      |
| ------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------ |
| External validation (MCD64A1), methodology documentation      | Production deployment, backups, _runbook_    | Accessibility (WCAG AA), e2e with Playwright           |
| All [REQ] met                                                 | Contract v1.0 frozen                         | User guide (`docs/user-guide.md`)                      |

---

## 5. Critical dependencies

```
M0 ──► A: complete QA ──► A: science (N07–N10) ──► M1 ──► A/B/C: harmonized product ──► M2
 │                                                  ▲
 ├──► B: API over real data (Peru / global) ────────┤
 └──► C: UI over the local server ──────────────────┘
```

- **Critical path:** N07 (observation opportunities, L2 masks). B and C are not blocked: they work on the
  real observations already imported.
- **Main risk:** that the calibration does not pass the thresholds. In that case the product keeps showing observations per
  instrument (as today) and the harmonized metric stays experimental. The API and the web do not change shape.

---

## 6. How to change a contract

| Change type  | Example                                                                           | Process                                                                                                                                                                                                                                                      |
| ------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Additive** | New optional field in a response, new endpoint, new column in `serving`           | The owner opens a PR prefixed `contract:`. Updates `models.py` (with `examples`) or the DDL, regenerates with `pnpm gen:types`, updates the seed if applicable, `API_CONTRACT.md` and its history. Bumps the minor version (0.1 → 0.2). The consumer approves. |
| **Breaking** | Renaming or removing a field, changing a type or a meaning                        | First a short RFC in `docs/contract-changes/NNNN-title.md` (reason, impact, migration). All 3 approve it. Then a `contract:` PR with a major version; in the API, the old field is marked _deprecated_ for one phase.                                        |
| **Internal** | Changing how something is computed without changing the contract                  | Normal PR by the owner. If the results of `stats` or of the harmonization change, `HARMONIZATION_VERSION` is bumped and an ADR is written (AGENTS §2.5).                                                                                                     |

Golden rule: **no agent changes a contract in the same PR as the implementation that consumes it in another area.**

---

## 7. Agents: how each one works

Each person runs their agent from the repo root. The agent reads:

1. `AGENTS.md` (root): global rules.
2. The `AGENTS.md` of its area (it prevails over the root one for files in that folder):
    - A: `packages/nina/AGENTS.md`
    - B: `apps/api/AGENTS.md`
    - C: `apps/web/AGENTS.md` (also covers `packages/ui` and `packages/config`)
3. `apps/api/API_CONTRACT.md` and this plan.

**Common rules:**

- They only write to the files of their role (§2). If they need something from another area, **they do not edit it**: they create
  `docs/requests/<target-role>-<slug>.md` (what, why, which contract it touches) or an issue labeled `needs:<role>`.
- They never edit `openapi.json`, `requirements.lock.txt` or `web/package-lock.json` by hand.
- They never import into or write to the database a running server uses (AGENTS §2.9).
- Before proposing a PR: `.\.venv\Scripts\python.exe -m pytest -q` and `npm.cmd --prefix web run build`.
- If a test or the build fails because of a change in another area, they **stop** and tell their person.
- Each PR links the plan task (e.g. `Phase 2 · A · N09`) and the acceptance criteria it covers.

---

## 8. Git and working rhythm

| Topic           | Rule                                                                                                                                           |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Branches        | `nina/<slug>`, `api/<slug>`, `web/<slug>`, `contract/<slug>`, `infra/<slug>`                                                                   |
| Main branch     | `main` protected: requires green CI and CODEOWNERS approval. _Squash merge_                                                                    |
| PR size         | ≤ 400 changed lines (not counting generated files, lockfiles or the seed)                                                                      |
| Syncing         | `git rebase origin/main` at least once a day                                                                                                   |
| Commits         | Conventional Commits with scope (AGENTS §16): `feat(nina): …`, `fix(api): …`, `feat(web): …`, `feat(ui): …`, `contract: …`, `chore(infra): …` |
| _Feature flags_ | Half-finished web features are hidden with `VITE_FEATURE_*` instead of waiting in a long-lived branch                                         |
| Meeting         | 15 min twice a week: milestone status, blockers, requests in `docs/requests/`                                                                  |
| Demo            | At the end of each phase, an end-to-end demo (even if only with the seed)                                                                     |

---

## 9. Definition of done per role

**Phases 0–2:**

- **A:** lint and typecheck of `@fire/nina` green; [REQ] criteria of the area reviewed; seed updated if `serving` changed.
- **B:** the endpoint matches API_CONTRACT, `openapi.json` and the types are regenerated, it works against the seed and the web builds.
- **C:** the feature works against the mocks **and** against the real API with the seed, and has loading, empty and error states.

**From Phase 3** the following is added:

- **A:** acceptance report generated in `source/reports/` and the required tests of AGENTS §15 green.
- **B:** Schemathesis green, tests over the seed and p95 met in staging.
- **C:** component test and axe without critical errors.

---

## 10. Cross-cutting product tasks (leadership tasks)

Features an MVP usually omits but that make the product look finished. Each one is split among the three
roles; they can start in parallel with the phases (they do not depend on the harmonization).

### T1 · Users and download management

**Today:** there are no accounts; anyone who opens the app can import, sync and export.

- **Accounts and roles:** sign-in (email + hashed password, or Google/GitHub login) and three roles:
  `visitor` (query only), `analyst` (exports, saves analyses), `admin` (imports, syncs FIRMS, trains models).
- **Protected routes:** `/api/import`, `/api/sync`, `/api/acquisitions*`, `/api/models/train` for `admin` only;
  exports only for authenticated users.
- **Download history:** a `downloads` table (user, analysis, type, rows, date, dataset version); a
  "My downloads" screen to download a file again with the same filters.
- **Saved and shareable analyses** per user (links already exist today; they get linked to their author).
- **Quotas and limits:** maximum rows per export and downloads per hour, with a clear message when exceeded.
- **Audit:** record of who imported, synced or deleted data and when.
- **Privacy:** do not store more personal data than necessary; FIRMS keys stay on the server only.

| A                                           | B                                                                    | C                                                             |
| ------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------- |
| Record the author in imports and batches    | Authentication, roles, `users`/`downloads`/`audit_log` tables, quotas | Login, sign-up, profile, "My downloads", no-permission states |

**Done when:** a visitor cannot import or export, an analyst sees their history and an admin sees the audit log.

### T2 · Input validation (dates, types, ranges)

**Today:** there are scattered validations (years 2000–2100, month 1–12, WGS84 polygon, `days` 1–5), but no common rules or uniform messages.

- **Dates:** `start ≤ end`; nothing before the sensor's first data (e.g. MODIS Terra 2000-11-01, S-NPP 2012-01-20)
  or after the last available day; nothing in the future; configurable maximum range.
- **Sensor consistency:** compatible product and platform (Aqua only with MODIS, NOAA-21 only from 2024, etc.).
- **Types and formats:** ISO `YYYY-MM-DD` dates, closed enumerations, maximum text lengths, maximum uploaded
  file size, CSV with the required FIRMS columns and UTF-8 encoding.
- **Geometry:** valid polygon, maximum area, inside the chosen scope (partly exists already; it gets unified).
- **Uniform errors:** a `422` response with a `code` and a message (_problem+json_ style), shown as is in the UI, in the interface language.
- **Double validation:** the UI validates before sending (disabled button and a message next to the field) and the server always validates.

| A                                                     | B                                                                                | C                                                                                         |
| ----------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Real coverage dates per sensor (from the database)    | Common validators in the Pydantic models, error codes, tests per rule            | Form validation, date picker bounded by coverage, error messages                          |

**Done when:** each rule has a test that sends an invalid value and receives its `code`, and the UI shows the message without breaking.

### T3 · Filtering by days (not only by months)

**Today:** selection is by year and month (`year_start`, `year_end`, `selected_year`, `selected_month`).

- **Free date range:** `date_start` / `date_end` (inclusive, UTC) in addition to the monthly mode; shortcuts such as
  "last 7 days", "last 30 days", "this season" or "this year".
- **Configurable aggregation:** day, week or month. Below 8 days the **sampling bias** warning is shown (AGENTS §8)
  and anomalies are not computed.
- **Daily calendar:** a view of days inside the selected month (GitHub-style heatmap) that keeps gap ≠ zero.
- **Time zone:** option to group by local date (e.g. `America/Lima`), with UTC by default.
- **Compatibility:** links and analyses saved with the monthly mode keep working.
- **Performance:** a date index or partition in DuckDB so short ranges respond quickly.

| A                                         | B                                                                                         | C                                                                         |
| ----------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Gaps and partials at the daily level too  | New fields in the selection, aggregation by day/week, export with the exact range         | Range picker with shortcuts, daily calendar view, bias warning            |

**Done when:** a 10-day range is chosen, hotspots are shown day by day and the export contains exactly those dates.

### Other "finished product" tasks (optional, they add up in the presentation)

| Task                           | What it brings                                                                    | Role  |
| ------------------------------ | --------------------------------------------------------------------------------- | ----- |
| Notifications / alerts         | Notice (email or in-app) when a saved region exceeds its historical median        | B + C |
| Accessibility (WCAG AA)        | Keyboard, contrast, screen reader, color-blind-safe palette                       | C     |
| Languages                      | ✅ `en`/`es` interface, English by default                                        | C     |
| Offline mode / cache           | The app opens with the latest data even if FIRMS fails                            | B     |
| Observability                  | Structured logs, status page, usage and error metrics                             | B     |
| "About the data" page          | Methodology, limitations, dataset version, FIRMS citation                         | A + C |
| Database backups               | Documented backup and restore of `nina.duckdb`                                    | B     |
| Onboarding                     | ✅ Landing page and platform guide for new users; extend as needed                | C     |
