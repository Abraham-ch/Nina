# NINA · Territorial fire evidence report (specification)

Status: implemented on branch `feat/territorial-report` (2026-11-14); web view pending. Owner: data/harmonization (backend) and UX/UI (web).

## 1. Purpose

Turn the harmonized record into a decision-ready document: a one-to-two-page **technical evidence report** for a
territory (country, department, province, district or drawn polygon) and a period. It answers, with verifiable figures:

1. Is the current fire activity anomalous with respect to its historical reference?
2. Is there a long-term trend once the sensor change is removed?
3. Does satellite-detected fire activity correspond to the emergencies recorded by the authorities?
4. How much forest cover was lost in areas with fire activity?
5. What were the climatic conditions (drought) during the period?

It is an annex of satellite context, not an official document and not a tactical product (FIRMS disclaimer).

## 2. Documented need (no interviews required)

| Procedure or document | What it requires | Section of the report that serves it |
|---|---|---|
| DS 074-2014-PCM (state of emergency): technical report, capacity exceeded, INDECI opinion | Evidence that the situation exceeds the normal range | §4.2 Current situation, §4.3 Historical context |
| Plan Multisectorial ante Incendios Forestales 2025–2027 (DS 010-2025-PCM): priority districts from the CENEPRED scenario | A consistent multi-year hotspot record per district | §4.3 Trend, §4.7 Priority table |
| Informe Defensorial 225 (2024), conclusion 9.1: no centralized official information on forest fires | A single, citable, reproducible source | Whole report, §4.9 Reproducibility |
| SERFOR fire monitoring (24-hour alerts) | Historical baseline for the current alerts | §4.2 Month to date |

## 3. Design principles

- Every figure comes from a server computation and carries its provenance (dataset id, query, date). The narrative
  text cannot introduce numbers that are not in the computed facts (automatic check).
- Missing data is shown as missing, never as zero; unvalidated domains abstain.
- Experimental status, FIRMS citation and disclaimer are always printed.
- Formal, technical language; bilingual (en/es).

## 4. Sections

| § | Section | Indicators | Data | Status |
|---|---|---|---|---|
| 4.1 | Header | Territory, period, cut-off date, dataset id, method version, validation status | Product manifest | Available |
| 4.2 | Current situation | Month to date and last complete month: VIIRS-equivalent active cell-days, anomaly vs median of other eligible years, rank, p10–p90 band; 12-month calendar strip | `/api/harmonized/analyses` (`selected`, `month_to_date`) | Available |
| 4.3 | Historical context | 2002–present series; rank of the season (Jul–Oct) and of the year; Theil–Sen trend with Mann–Kendall p-value, harmonized **and** raw, to show the sensor artefact | Harmonized product; raw pixel counts | **Available** |
| 4.4 | Detected fire events vs recorded emergencies | Fire events from spatio-temporal clustering of harmonized cell-days (neighbouring cells, gap ≤ 2 days); count, duration, extent; INDECI forest-fire emergencies for the same territory and period; ratio | Harmonized product; INDECI/SINPAD open data (ubigeo) | **Available** (Peru) |
| 4.5 | Forest cover loss associated with fire | Tree-cover loss (ha) in cells with fire activity in the same or previous year; share of total loss; comparison with previous years | Hansen/UMD Global Forest Change (loss year, 30 m); MINAM Geobosques as national reference | **Available** (Peru) |
| 4.6 | Climatic conditions | Precipitation and soil-moisture anomaly (z-score) for the period; drought flag. Context only: no causal attribution | NASA POWER v2.10 (MERRA-2); SENAMHI PISCO as a future national option | **Available** (Peru, 2001–2025) |
| 4.7 | Priority table (country/department level) | Sub-territories ranked by transparent indicators (anomaly, trend, events/emergencies ratio, forest loss), each shown separately; no opaque composite score | Sections 4.2–4.5 | Partial: subdivision table of events vs emergencies |
| 4.8 | Visual evidence | Before/after true-colour imagery for the period; map of harmonized cells | NASA GIBS (already used by the web) | Pending (web) |
| 4.9 | Quality and limits | Valid region-days, NOAA-20-filled days, unvalidated share, typical yearly error (±10 % MODIS era), FIRMS disclaimer | Analysis fields, validation report | Available |
| 4.10 | Reproducibility | Dataset id and hashes, request parameters, generation time, links to the method (ADR 0002–0005) | Manifest | Available |

The executive summary (3–5 sentences) is written by the analytical assistant from the computed facts of §4.2–4.6 and
validated: any number in the text must match a fact.

## 5. Interface

### API (backend)

- `POST /api/reports/territorial` → `{selection, period, language}`; returns the report as JSON: sections with
  facts, provenance and status per section (`available`, `not_available`, `unvalidated`).
- `GET /api/reports/territorial/{id}` → the same JSON.
- `GET /api/reports/territorial/{id}/document` → printable HTML (and PDF when a renderer is configured), with the
  FIRMS citation and disclaimer.

### Web

- A **Generate report** action in the territory panel (country, department, polygon) and in the calendar.
- A report view with print styles (A4), section anchors, charts (calendar strip, series with p10–p90 band, trend raw
  vs harmonized), the priority table and the before/after images.
- Download as PDF and as ZIP (JSON facts + CSV + README with citation).

## 6. Validation of each section

- 4.2–4.3: covered by the harmonized product validation (leave-one-year-out, INPE agreement r = 0.95).
- 4.4: parameters of the clustering tested against INDECI events by district and against the Global Fire Atlas
  (MODIS burned-area fires) where they overlap.
- 4.5: totals compared with Geobosques annual loss for Peru.
- 4.6: sources compared with each other (GPM vs PISCO) for Peru.
- Assistant: evaluation set of specialist questions, including unanswerable ones; results published.

## 7. Out of scope

Fire forecasting, spread modelling, causal attribution of individual fires, tactical use, and generated imagery.

## 8. Implementation and validation (2026-11-14)

| Layer | Build | Output | Validation |
|---|---|---|---|
| Districts | `nina.io.territory` | `source/context/districts/` (1,826 districts with UBIGEO, 218,676 H3 cells) | Source: INEI/MINAM limits via github.com/juaneladio/peru-geojson (MPL-2.0); 8 small districts have no geometry |
| INDECI emergencies | `nina.io.territory` | `source/context/indeci/forest_fire_emergencies.parquet` (4,798 records, 2003 – 2026-06-30) | Every record kept; dates checked against the stated year and month (mixed day-first/month-first formats); 159 codes of districts newer than the boundary layer are matched by prefix |
| Fire events | `nina.io.territory` | `source/context/events/` (Peru: 481,871 events from 817,698 cell-days; 18,010 with ≥ 5 cell-days) | Rule from FET / ST-DBSCAN practice (≈ 2 km neighbourhood, ≤ 2-day gap); compare years within the VIIRS era only |
| Forest loss | `nina.io.forest_loss` | `source/context/forest_loss/` (Hansen GFC-2024-v1.12, 0.005° blocks → H3) | Peru totals 2001–2024 within 0.3–0.6 % of Global Forest Watch; MINAM Geobosques differs by design (humid Amazon forest only) |
| Climate | `nina.io.climate` | `source/context/climate/climate_department_month.parquet` (26 units × 2001–2025) | Reproduces the Amazon droughts of 2005, 2023 and 2024 in Aug–Sep; 2016 not visible in Aug–Sep (drought centred in Brazil, Oct–Mar) |

API: `POST /api/reports/territorial` with `{"ubigeo": "25", "year": 2024, "month": 9, "language": "es"}` (or `country`,
or `geometry`, or `place_name` with a Peruvian department name); `GET /api/reports/territorial/{id}/document` returns
the printable page. A report takes 0.5–2 s.

Delivered with the report (branch `feat/territorial-report`):

| Piece | Where | Status |
|---|---|---|
| Printable A4 document (KPI cards, seasonal band, year × month heatmap, indexed trend raw vs harmonized, events vs emergencies, forest loss, climate table, quality) | `nina/report_document.py` | Done |
| Before/after imagery from NASA GIBS (peak day of the month and 60 days earlier; NOAA-20 → S-NPP → MODIS layer fallback; blank-tile check) | `GET /api/reports/territorial/{id}/imagery/{before\|after}` | Done |
| Priority table of Peru's 25 departments, one column per indicator, no composite score | `POST /api/reports/priority`, tab "Priorities" | Done |
| "Technical report" buttons in the atlas brief and the calendar | `web/src/ReportButton.tsx` | Done |
| Analytical assistant with tools and figure verification | `/api/analyst`, [ANALYST.md](ANALYST.md) | Done (deterministic engine evaluated; model engine pending a key) |
| PDF renderer and ZIP download | — | Pending (the browser prints the page to PDF) |

Department names sent from the map are resolved to INEI districts, while the map draws geoBoundaries outlines; values
can differ by a few percent between the two (Ucayali, September 2024: 4,582 on the map, 4,491 in the report).
