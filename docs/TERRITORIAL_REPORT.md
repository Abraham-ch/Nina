# NINA · Territorial fire evidence report (specification)

Status: proposed, 2026-11-14. Owner: data/harmonization (backend) and UX/UI (web).

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
| 4.3 | Historical context | 2002–present series; rank of the season (Jul–Oct) and of the year; Theil–Sen trend with Mann–Kendall p-value, harmonized **and** raw, to show the sensor artefact | Harmonized product; raw pixel counts | Computation exists (`scripts/evidence`); endpoint to build |
| 4.4 | Detected fire events vs recorded emergencies | Fire events from spatio-temporal clustering of harmonized cell-days (neighbouring cells, gap ≤ 2 days); count, duration, extent; INDECI forest-fire emergencies for the same territory and period; ratio | Harmonized product; INDECI/SINPAD open data (ubigeo) | To build (clustering + district boundaries with ubigeo) |
| 4.5 | Forest cover loss associated with fire | Tree-cover loss (ha) in cells with fire activity in the same or previous year; share of total loss; comparison with previous years | Hansen/UMD Global Forest Change (loss year, 30 m); MINAM Geobosques as national reference | To build (tile download, aggregation to H3) |
| 4.6 | Climatic conditions | Precipitation and soil-moisture anomaly (z-score) for the period; drought flag. Context only: no causal attribution | NASA GPM IMERG or POWER, SMAP; SENAMHI PISCO as national option | To build |
| 4.7 | Priority table (country/department level) | Sub-territories ranked by transparent indicators (anomaly, trend, events/emergencies ratio, forest loss), each shown separately; no opaque composite score | Sections 4.2–4.5 | To build |
| 4.8 | Visual evidence | Before/after true-colour imagery for the period; map of harmonized cells | NASA GIBS (already used by the web) | Partly available |
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
