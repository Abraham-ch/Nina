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
- A report in three levels: a summary page (headline, four key figures, this year against the normal range, key
  points), the evidence (trend raw vs harmonized, detected events vs registered emergencies with their validation,
  forest loss, before/after images) and an annex (activity calendar, subdivisions, climate, quality, sources).
- **Download PDF** (the browser's print dialog, "Save as PDF", with A4 page breaks between the levels) and
  **Download data (ZIP)**: `GET /api/reports/territorial/{id}/package` returns the self-contained report (images
  embedded), `report.json`, CSV tables (UTF-8 with BOM) and a `README.txt` with the FIRMS citation and disclaimer,
  dataset version, request and generation date.

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
| Fire events | `nina.io.territory --countries Peru Brazil Australia Indonesia "United States of America"` | `source/context/events/` — Peru 481,871 events (817,698 cell-days); Brazil 5,061,395 (10,995,584); Australia 1,171,678 (6,130,324); Indonesia 1,007,134 (2,196,283); United States 1,523,587 (2,731,152) | Rule from FET / ST-DBSCAN practice (≈ 2 km neighbourhood, ≤ 2-day gap); compare years within the VIIRS era only; validated against registries (below) |
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
| PDF and ZIP download | Document toolbar; `GET /api/reports/territorial/{id}/package` | Done (PDF through the browser's print dialog; no server-side PDF renderer) |

Department names sent from the map are resolved to INEI districts, while the map draws geoBoundaries outlines; values
can differ by a few percent between the two (Ucayali, September 2024: 4,582 on the map, 4,491 in the report).

## 9. Validation against independent records (2026-11-15)

Code: `packages/nina/src/nina/io/context_validation.py`; outputs in `source/context/validation/*.json`, read by the
report (green notes under each chart) and by the analytical assistant.

### Fire events vs INDECI emergencies (Peru)

Every INDECI forest-fire emergency with a real date in the VIIRS era (4,367 records, 17 Apr 2012 – 30 Jun 2026; 159
records of districts newer than the boundary layer are excluded) is matched against the harmonized fire events touching
its district (plus a one-cell border, about 2.5 km). The chance level repeats the match with the same district and the
date shifted one year earlier and later: it keeps place and season, so it is a demanding baseline.

| Measure | Observed | Chance level |
|---|---|---|
| Emergencies with a detected event within ±1 day | 56.7 % | 21.4 % |
| Emergencies with a detected event within ±3 days | 67.2 % | 33.6 % |
| Emergencies with a significant event (≥ 5 cell-days) within ±3 days | 17.9 % | 6.6 % |
| Significant events with a registered emergency within ±3 days | 7.5 % | 3.9 % |
| Department totals, events vs emergencies (Spearman, 24 departments) | ρ = 0.36 (p = 0.08) | — |
| Department-years (318 pairs) | ρ = 0.10 (p = 0.09) | — |

Reading: detected events and registered emergencies are associated in place and time (two to three times the chance
level), but they are not interchangeable. Satellites see almost every registered emergency in the Amazon (Ucayali
99 %, Madre de Dios 98 %, San Martín 97 %; there fires are so frequent that chance alone reaches 89 % in Ucayali), and
fewer in the Andes (Cusco 59 %, Puno 60 %, Apurímac 63 %), where many registered fires are small or under cloud. Most
satellite-detected fires are never registered (only 7.5 % of significant events are). The report therefore shows both
and never presents one as a check of the other.

Sensitivity of the clustering gap (VIIRS era): gap of 1, 2 or 3 days gives 13,192, 15,324 or 16,228 significant
events; detection of emergencies by significant events 15.8 %, 17.9 %, 19.9 %; registered share 7.9 %, 7.5 %, 7.4 %.
The 2-day rule is not a fragile choice.

### Fire events vs registries of the other four countries

Same method (registered record ↔ detected event in the same place and window; chance = same place and date one year
earlier and later). Registries are normalised by `packages/nina/src/nina/io/registries.py` into
`source/context/registries/` with every excluded row counted.

| Country | Registry | Records (period) | Zone, window | Detected | Chance | Significant events registered (chance) |
|---|---|---|---|---|---|---|
| United States | NIFC/WFIGS wildfire incidents (IRWIN) | 6,499 of ≥ 400 ha among 392,595 (Feb 2014 – Nov 2026) | point + 2 rings (≈ 5 km), −2/+7 days | **85.7 %** | 5.1 % | 22.3 % (6.8 %) |
| Australia | Geoscience Australia mapped bushfires (prescribed burns excluded) | 3,982 of ≥ 400 ha among 24,165 (2012 – Aug 2025) | centroid + 2 rings, −2/+7 days | **79.8 %** | 20.0 % | 3.5 % (1.2 %) |
| Indonesia | BNPB/DIBI forest and land fires (DesInventar export) | 1,679 (2012 – Dec 2019) | regency cells + 1 ring, ±3 days | 81.3 % | 62.2 % | 3.4 % (1.7 %) |
| Brazil | IBAMA/Prevfogo fire occurrences (federal brigades) | 4,676 (Dec 2014 – Nov 2022) | municipality cells + 1 ring, −3/+7 days | 98.9 % | 97.7 % | 4.0 % (3.4 %) |

United States by fire size (all 392,595 records): ≥ 4,000 ha 93.0 % (chance 1.9 %); 400–4,000 ha 83.4 % (6.1 %);
40–400 ha 62.3 % (8.2 %); < 40 ha 9.2 % (3.4 %). Australia: 77.6 %, 81.1 %, 73.0 % and 41.2 % for the same classes.

Reading:
- Where the registry gives a point and a size (United States, Australia), detection of large fires is 80–93 %, four to
  forty times the chance level, and it falls with fire size as expected from the sensor resolution.
- Where records are placed only by a large administrative unit (Brazilian municipalities, Indonesian regencies), the
  chance level is high because fire is detected there almost every week; the Brazilian comparison is **not
  informative** (lift of 1 point) and the report says so instead of showing a high rate as success. The Indonesian
  export ends in 2019 and under-records large seasons (2015: 46 records).
- In every country only a small share of satellite events is registered: registries record incidents that agencies
  attended, not all fire activity.
- Not used: Brazil's civil-defence S2iD/Atlas Digital (the portal blocks scripted access; to be added when downloaded
  manually), Indonesia after 2019 (the live DIBI dashboard is compromised; BNPB's public service holds only the
  current week), the Global Fire Atlas (MODIS burned-area objects; large files, left for later).

### Tree-cover loss vs MINAM Geobosques (Peru)

Hansen/UMD annual loss aggregated to INEI departments against Geobosques humid-Amazon-forest loss (Excel by department
"al 2025", 2001–2024; 12 departments with at least 10,000 ha of loss).

| Measure | Result |
|---|---|
| Ranking of departments by total loss (Spearman) | 0.99 |
| Hansen / Geobosques national total | 1.36 (Hansen includes all tree cover ≥ 30 % and fire-killed forest) |
| Year-to-year national agreement 2001–2024 | 0.76 |
| … 2001–2011 | 0.95 |
| … 2012–2024 | −0.02 |
| Median department agreement (12 departments) | 0.83 (Madre de Dios 0.96, Ucayali 0.94; San Martín 0.37, Cajamarca 0.51) |

Reading: the layer is reliable for comparing places and the scale of loss; national year-to-year changes after 2012 do
not agree with the official series (Hansen's 2011–2012 method change and fire-driven canopy loss in drought years
are the likely reasons; the second is a hypothesis). The report states this under the forest chart.

### Climate (NASA POWER) vs CHIRPS

Monthly precipitation anomalies (z against 2002–2024, same calendar month) of NASA POWER (MERRA-2, ~0.5°) against
CHIRPS v2.0 (satellite and gauges, 0.05°, read from the monthly COGs over the Peru window), by INEI department,
2002–2025, months with at least 10 mm of normal rainfall:

| Measure | Result |
|---|---|
| Correlation of anomalies, median of 24 departments | r = 0.45 (pooled 0.43); lowest Tacna 0.14, Áncash 0.14, Lima 0.20; highest Tumbes 0.75, Madre de Dios 0.61 |
| Drought flag (rainfall z ≤ −1 and VPD z ≥ +1) with POWER vs CHIRPS rainfall | same value in 94.3 % of department-months |
| POWER drought months confirmed by CHIRPS (z ≤ −0.5) | 69.5 % of 318 |

**Method change (context layer, not the harmonization):** because reanalysis rainfall agrees only moderately with
the gauge-corrected product, the climate section now takes rainfall (amount, percentile, anomaly) from CHIRPS and keeps
NASA POWER only for air dryness (vapour-pressure deficit); the drought flag uses CHIRPS rainfall. Where CHIRPS has no
value (Lima Metropolitana as a separate unit; months after the last CHIRPS file) the report falls back to POWER and
says which source it used (`precip_source`). PISCO (SENAMHI) was not used: its public series ends in 2016 (stable)
or February 2019, and the public FTP server showed signs of tampering on 2026-11-15.
