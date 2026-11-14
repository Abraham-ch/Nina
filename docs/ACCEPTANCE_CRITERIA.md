# Acceptance criteria · Hotspot processing and harmonization

> Location in the repo: `docs/ACCEPTANCE_CRITERIA.md`
> Applies to every processing change: `nina/ingest.py`, `nina/global_ingest.py`, `nina/remote.py`, `nina/science.py` and `scripts/`.
> The current MVP meets only part of these criteria: those not implemented are reported as `pending`.
> Complements `AGENTS.md` (§5–§10). In case of conflict, **this file prevails** for data processing.

## How to use this document (instructions for the agent)

1. Before starting, identify which criteria your task touches (**Area** column).
2. An **[REQ]** (required) criterion cannot be left unmet. A **[REC]** (recommended) one can be
   postponed, but you must note it in the report as `pending` and explain why.
3. Each criterion states **how it is verified**: an automated test, a generated artifact or a review.
   If the test does not exist, create it; do not mark the criterion as met without evidence.
4. When finished, generate `data/reports/acceptance_<run_id>.md` with the template at the end, stating for each
   affected criterion whether it is `met`, `not met`, `not applicable` or `pending`, together with its evidence.
5. Criteria format: **Given** (context) · **When** (action) · **Then** (expected result).

### Sources cited

| Key        | Document                                                              |
| ---------- | --------------------------------------------------------------------- |
| **GUIDE**  | _MODIS C6/C6.1 Active Fire Product User's Guide_ v1.0 (Giglio et al.) |
| **README** | `Readme.txt` included in NASA FIRMS downloads                         |
| **C61**    | _MODIS C61 Land – Proposed Changes_                                   |
| **AGENTS** | `AGENTS.md` of this repository                                        |

---

## 1. Ingestion and data origin (ING)

**ING-01 [REQ] · Origin identified by file name**

- Given a FIRMS ZIP or file with prefix `DL_FIRE_M-C61`, `DL_FIRE_SV-C2`, `DL_FIRE_J1V-C2` or `DL_FIRE_J2V-C2`,
- when it is ingested,
- then each row receives `instrument`, `satellite_norm` and `source_file` consistent with the prefix, and
  `DL_FIRE_LS_*` (Landsat) files are excluded with `qa_reason = "excluded_instrument"`.
- _Verification:_ `test_ingest_detects_source_from_filename` with one file per prefix.
- _Source:_ README.

**ING-02 [REQ] · Standard vs. NRT quality**

- Given a `fire_archive_*` or `fire_nrt_*` file,
- when it is ingested,
- then `quality_level` is `standard` or `nrt` according to the name. If the name does not say, the
  `version` field is used (if it contains `NRT`, it is `nrt`).
- _Verification:_ parameterized test with both file types and with versions `"6.1NRT"`, `"61.03"`, `"2.0NRT"`, `"2"`.
- _Source:_ README.

**ING-03 [REQ] · Precedence of standard data over NRT**

- Given that standard and NRT data exist for the same `satellite_norm` and the same `acq_date_utc`,
- when consolidating,
- then only the standard data are kept and the NRT data are recorded with `qa_reason = "superseded_by_standard"`.
- _Verification:_ `test_standard_supersedes_nrt`; the QA report shows the count.
- _Source:_ README (NRT data are replaced about 3 months later).

**ING-04 [REQ] · NOAA-20 and NOAA-21 quality according to what exists**

- Given NOAA-20 or NOAA-21 data,
- when they are ingested,
- then `quality_level` is determined by the real source (`VIIRS_NOAA20_SP` → `standard`; `*_NRT` → `nrt`) and **not** by a
  fixed rule. Which sensors have standard data, and up to which date, is queried in `/api/data_availability` (ING-09).
  NOAA-21 remains NRT-only until that query says otherwise.
- _Verification:_ test with simulated `data_availability` responses.
- _Source:_ README (it says there are no standard NOAA-20/21 data; **it is out of date**: the API already offers `VIIRS_NOAA20_SP`).

**ING-05 [REQ] · Empty downloads**

- Given a CSV with only a header, an empty DBF or a JSON `[]`,
- when it is ingested,
- then the process ends without error, records `0 rows` for that file and continues.
- _Verification:_ `test_empty_inputs` with the three cases.
- _Source:_ README.

**ING-06 [REQ] · Encoding and projection**

- Given any input file,
- when it is read,
- then it is read as UTF-8 (tolerating a BOM), coordinates are treated as EPSG:4326 and no attempt is made to parse
  `Readme.txt` (it contains badly encoded characters).
- _Verification:_ test with a fixture that has a BOM; code review.
- _Source:_ README.

**ING-07 [REQ] · Global reference data to detect gaps**

- Given that a region of interest is processed,
- when coverage and gaps are computed (GAP-02),
- then **global (or wide-area) daily counts per satellite** are used, not only those of the region.
  Suggested source: monthly MCD14ML files (University of Maryland SFTP) or a global FIRMS download.
- _Verification:_ `data/interim/global_daily_counts.parquet` exists with columns `satellite_norm`, `date`, `n`.
- _Source:_ GUIDE §7.1.1 (hotspot files do not report missing data) and §4.3.

---

## 2. Schema and types (SCH)

**SCH-01 [REQ] · JSON input contract**

- Given a `.json` whose root is an array of objects,
- when it is validated against `hotspot_input.schema.json`,
- then the fields of AGENTS §6 are accepted and rows missing any required field are rejected with `schema_invalid`.
- _Verification:_ `test_schema_valid_modis_example` (example object from `data_type`) and `test_schema_invalid_rows`.
- _Source:_ AGENTS §6.

**SCH-02 [REQ] · Numeric fields arriving as text**

- Given `confidence: "48"`, `type: "0"` and `acq_time: "0000"`,
- when they are normalized,
- then `confidence_raw = "48"` with class `nominal`, `hotspot_type = 0` and time `00:00 UTC` are obtained.
  In addition, `acq_time` given as `"618"` or `618` is interpreted as `06:18 UTC`.
- _Verification:_ parameterized test.
- _Source:_ AGENTS §6.1, GUIDE §5.5 (Table 10: `HHMM` in UTC).

**SCH-03 [REQ] · Collection and version**

- Given a MODIS record with a Collection 6 or 6.1 `version` (`"6.0"`, `"6.1"`, `"61.03"`, `"6.1NRT"`, etc.),
- when it is normalized,
- then it is accepted **without applying any adjustment** between C6 and C6.1. A record from an earlier collection (starting
  with `5` or `4`) is rejected with `qa_reason = "unsupported_collection"`.
- _Verification:_ parameterized version test.
- _Source:_ GUIDE §2.1 (C6 and C6.1 can be mixed; FRP unchanged; global difference of 0.001 %), C61 (calibration changes
  affect bands 1 and 2, not the thermal ones), GUIDE §7.3 (C5 issues must not get in).

**SCH-04 [REQ] · Brightness fields per instrument**

- Given a MODIS record (`brightness`, `bright_t31`) or a VIIRS one (`bright_ti4`, `bright_ti5`, or their aliases `brightness` and `brightness_2`),
- when it is normalized,
- then they are mapped to `bt_mir_k` and `bt_tir_k` without losing the original value.
- _Verification:_ test with a fixture for each instrument.
- _Source:_ AGENTS §7.1.

---

## 3. Temporal domain (TMP)

**TMP-01 [REQ] · Series start date**

- Given a MODIS record with `acq_datetime_utc < 2000-11-01`,
- when it is validated,
- then it is rejected with `qa_reason = "pre_nov2000_quality"`.
- _Verification:_ `test_rejects_pre_november_2000`.
- _Source:_ GUIDE §7.2.1 (before Nov 2000 there were damaged detectors, striping, undetected fires and, in Feb–Mar 2000,
  whole scan lines flagged as fire) and GUIDE §8.3.10.

**TMP-02 [REQ] · Time in UTC**

- Given any record,
- when it is stored,
- then `acq_datetime_utc` is in UTC. Conversion to local time only happens in the API or the UI.
- _Verification:_ test and schema review (`timestamptz`).
- _Source:_ GUIDE §5.5 (Table 10), AGENTS §8.

**TMP-03 [REQ] · Coverage computed from the data**

- Given a pipeline run,
- when it ends,
- then the `coverage` table has real `first_date` and `last_date` per `satellite_norm` and `quality_level`.
  Fixed dates written in the code are not accepted.
- _Verification:_ `coverage` artifact + test.
- _Source:_ AGENTS §5.3.

**TMP-04 [REQ] · Climatology with complete years**

- Given the monthly climatology computation,
- when the reference years are defined,
- then **2001 → last complete year** is used by default. 2000 (incomplete, and not reliable before Nov 2000) is excluded,
  as are months that do not meet GAP-04.
- _Verification:_ test on the climatology function.
- _Source:_ GUIDE §7.2.1, AGENTS §8.

---

## 4. Gaps and observation coverage (GAP)

**GAP-01 [REQ] · Catalog of known gaps**

- Given `docs/reference/known_gaps.yaml`,
- when it is reviewed,
- then it contains **at least** these periods, each with its source:

    | Satellite | Period                                                                                    | Source      |
    | --------- | ----------------------------------------------------------------------------------------- | ----------- |
    | Terra     | before 2000-11-01 (hardware and calibration problems)                                     | GUIDE §7.2.1 |
    | Terra     | September 2000 (instrument inoperative)                                                   | GUIDE §8.3.3 |
    | MODIS     | late June to early July 2001                                                              | README      |
    | MODIS     | 2002, intermittent gaps                                                                   | README      |
    | MODIS     | from mid-August 2007                                                                      | README      |
    | MODIS     | 21 Apr 2009 (partial) and 22 Apr 2009 (complete)                                          | README      |
    | **Aqua**  | **16 Aug 2020 → 02 Sep 2020** (FMU failure; coverage limited to direct broadcast)         | GUIDE §7.2.4 |

- _Verification:_ test that loads the YAML and checks that these periods are present.

**GAP-02 [REQ] · Automatic gap detection**

- Given the global daily counts (ING-07),
- when a satellite has 0 global detections on a day, or a count below 10 % of the 31-day rolling median,
- then that day is recorded in `data_gaps` with `reason = "detected_outage"`, even if it is not listed in GAP-01.
- _Verification:_ `test_detects_outage` with a synthetic series containing an outage.
- _Source:_ GUIDE §7.1.1 and §8.3.3, README.

**GAP-03 [REQ] · A gap is not a zero**

- Given a day or month of a region without a valid observation,
- when the aggregates are generated (`harmonized_cell_day`, calendar),
- then the value is `data_gap = true` with the count as `null`, **never** `0`.
- _Verification:_ `test_gap_is_not_zero` with the 2020 Aqua period and with 22 Apr 2009.
- _Source:_ GUIDE §7.1.1 (a missing hotspot does not imply there was no fire).

**GAP-04 [REQ] · Partial MODIS coverage (Terra or Aqua missing)**

- Given a day on which only one of the two satellites, Terra or Aqua, has data,
- when combined MODIS is aggregated,
- then the day is marked `partial_coverage = true`. A month with more than 20 % of days with a gap or partial coverage is
  excluded from calibration (HAR) and climatology (TMP-04) and shown in the UI as "incomplete coverage".
- _Verification:_ test with August 2020 (Aqua missing, Terra present).
- _Source:_ GUIDE §7.2.4.

**GAP-06 [REQ] · Official FIRMS gaps**

- Given the FIRMS `missing_data` service (DATA_SOURCES §1.2),
- when `data_gaps` is updated,
- then the dates FIRMS publishes as missing (standard and NRT, per satellite) are added with `reason = "firms_missing_data"`.
  This complements GAP-01 and GAP-02; it does not replace them.
- _Verification:_ test with a simulated response; the QA report counts gaps by origin.

**GAP-07 [REQ] · End of mission is not a gap**

- Given a satellite that ended its mission (S-NPP from 2026-11-02 13:00 UTC, and Terra or Aqua when applicable),
- when there are no detections after that date,
- then the `coverage` table records `end_of_mission` and those days are **not** marked as `detected_outage` or `data_gap`.
  The date is configured in `sensor_lifecycle.yaml`, never in the code.
- _Verification:_ `test_end_of_mission_not_gap` with S-NPP in November 2026.
- _Source:_ NASA/NESDIS notice about the end of S-NPP.

**GAP-05 [REC] · Cloudiness and observability**

- Given the MODIS monthly gridded products (MOD14CMQ/MYD14CMQ, 0.25°), with the layers `MeanCloudFraction`, `TotalPix` and `CloudCorrFirePix`,
- when they are integrated,
- then each cell-month with `MeanCloudFraction > 0.6` (configurable) is marked `low_observability`, and the ratio
  `CloudCorrFirePix / RawFirePix` is stored as an indicator of how much the counts could be underestimated.
- _Verification:_ `cloud_observability.parquet` artifact and a reading test.
- _Source:_ GUIDE §3.6, §5.4.2 and §7.1.1.

---

## 5. Detection confidence (CONF)

**CONF-01 [REQ] · MODIS thresholds**

- Given a MODIS confidence value `C`,
- when it is classified,
- then it is `low` if `0 ≤ C < 30`, `nominal` if `30 ≤ C < 80` and `high` if `80 ≤ C ≤ 100`. A value outside 0–100
  or non-numeric is recorded as `schema_invalid`.
- _Verification:_ test with the boundary values `29, 30, 79, 80, 100, 101, "abc"`.
- _Source:_ GUIDE §8.4.3 (Table 11).

**CONF-02 [REQ] · VIIRS classes**

- Given `l`, `n` and `h`, then they are classified as `low`, `nominal` and `high`. Any other value is `schema_invalid`.
- _Verification:_ test.

**CONF-03 [REQ] · Default filter**

- Given the default configuration,
- when filtering,
- then only `nominal` and `high` detections are kept; `low` ones are recorded as `low_confidence`.
  The threshold can be changed with `MIN_CONFIDENCE_CLASS`.
- _Verification:_ test and `low_confidence` count in the QA report.
- _Source:_ GUIDE §5.1.3 and §8.4.2 (to reduce false alarms, using only nominal and high is recommended).

**CONF-04 [REQ] · Confidence is not used as a weight**

- Given any aggregation or calibration,
- then confidence is only used as a **filter**, never as a weighting.
- _Verification:_ code review.
- _Source:_ GUIDE §7.2.2 (some doubtful pixels are still classified as nominal), AGENTS §9.2.

---

## 6. Hotspot type and static sources (TYPE)

**TYPE-01 [REQ] · Filter by `type` in standard data**

- Given a record with the `type` field,
- when filtering,
- then only `type = 0` (presumed vegetation fire) is kept. `1` (active volcano), `2` (other static land
  source) and `3` (offshore) are recorded as `non_vegetation_type`.
- _Verification:_ parameterized test.
- _Source:_ GUIDE §5.5 (Table 10).

**TYPE-02 [REQ] · Static-source mask with the guide's criterion**

- Given VIIRS and NRT hotspots, which do not carry `type`, and also standard MODIS,
- when `static_source_mask` is built,
- then a ~1 km cell (H3 res. 8, configurable) is marked as static if it had detections on **16 or more days
  of the same calendar year**, or if it is in an **urban area**, or within 2 km (configurable) of an **active volcano**,
  or over **water** (possible offshore gas flaring).
- _Verification:_ test with a synthetic series of 16 and 15 days; `static_source_mask.parquet` artifact.
- _Source:_ GUIDE §5.5 (definition of `type = 2`: 16 or more days in a calendar year, plus urban areas from MCD12Q1;
  `type` 0–2 are land only and 3 corresponds to water).

**TYPE-03 [REQ] · The mask also applies to MODIS with `type = 0`**

- Given a standard MODIS hotspot with `type = 0` that falls in a `static_source_mask` cell,
- when filtering,
- then it is excluded with `qa_reason = "static_source_mask"`, and the QA report shows how many `type = 0` the mask captured.
- _Verification:_ test and count in the report.
- _Source:_ GUIDE §7.2.3 (some static sources are not flagged in `type`).

**TYPE-04 [REQ] · Validation of the mask against MODIS `type = 2`**

- Given the overlap period with standard MODIS data,
- when the mask built from VIIRS data is compared against MODIS cells with `type ∈ {1, 2}`,
- then the mask recovers **at least 80 %** of those cells and removes **at most 2 %** of MODIS `type = 0`
  detections (configurable and documented thresholds).
- _Verification:_ `data/reports/static_mask_validation_<version>.json` artifact; the flow fails if the thresholds are not met.
- _Source:_ GUIDE §5.5 and §7.2.3.

**TYPE-05 [REQ] · Auxiliary data for the mask**

- Given the mask,
- then it uses: urban areas from **MCD12Q1** (IGBP class 13, "Urban and Built-up"), with GHSL as an alternative;
  volcanoes from the **Smithsonian GVP**; and a land/water mask. Each source is recorded in `data/sources.yaml` (see AUX-01).
- _Verification:_ review of `sources.yaml` and a loading test.
- _Source:_ GUIDE §5.5 and C61 (MCD12Q1 C6.1 has a minor fix in the UMD class; use the C6.1 version).

---

## 7. Pixel geometry (PIX)

**PIX-01 [REQ] · Pixel area**

- Given `scan` and `track` (in km),
- when normalizing,
- then `pixel_area_km2 = scan × track` is computed and kept.
- _Verification:_ test (for the `data_type` example: 2.5 × 1.5 = 3.75 km²).
- _Source:_ GUIDE §8.4.6 (the MODIS pixel is nominally 1 km² and grows away from nadir).

**PIX-02 [REQ] · Cell counting does not depend on pixel size**

- Given two hotspots from the same satellite and the same overpass that fall in the same aggregation H3 cell,
- when `active` is computed (AGENTS §10.1),
- then the cell counts **only once**.
- _Verification:_ `test_cell_counts_once`.
- _Source:_ GUIDE §7.1.1 (risk of misusing pixel locations).

**PIX-03 [REC] · Sensitivity to scan angle**

- Given the overlap period,
- when the harmonization is validated,
- then the report includes a comparison of results with and without hotspots where `pixel_area_km2 > 4` (configurable).
- _Verification:_ section present in `validation_<version>.json`.
- _Source:_ GUIDE §8.4.6.

---

## 8. Temporal resolution and sampling bias (SAMP)

**SAMP-01 [REQ] · Main calendar unit**

- Given the aggregates for the app,
- when the calendar products are generated,
- then the main unit is **monthly**, and anomalies and rankings are only computed with aggregations of **8 days or more**.
- _Verification:_ test on the anomaly function: `freq="day"` must raise `ValueError` or return the `sampling_bias` warning.
- _Source:_ GUIDE §7.1.1 (severe biases at intervals shorter than about 8 days) and §8.6.2.

**SAMP-02 [REQ] · Warning on daily outputs**

- Given a daily output (series or aggregated CSV),
- then it includes `sampling_bias_warning = true` in its metadata and the API propagates it to the UI.
- _Verification:_ contract test of `/timeseries?freq=day`.
- _Source:_ GUIDE §7.1.1.

**SAMP-03 [REQ] · Combining Terra and Aqua**

- Given Terra and Aqua,
- when MODIS is aggregated,
- then both are combined into a single MODIS series (like the MCD14ML product, which brings both together). Aqua does not exist before
  July 2002, and the calibration must account for that change in sampling frequency: stratum `modis_terra_only`
  before Jul 2002 and `modis_terra_aqua` from then on.
- _Verification:_ test and separate calibration coefficients.
- _Source:_ GUIDE §3.7 and §8.6.2 (with a single instrument sampling is insufficient over short periods).

---

## 9. MODIS ↔ VIIRS harmonization (HAR)

**HAR-01 [REQ] · Stratification**

- Given the calibration fit,
- then it is estimated per **biome or ecoregion** (e.g. RESOLVE Ecoregions 2017) **× calendar month** and **× sampling stratum**
  (SAMP-03). If a stratum has fewer than 30 cell-months with activity, the higher stratum is used (biome → region → global).
- _Verification:_ `calibration_<version>.parquet` artifact with columns `stratum`, `month`, `sampling_stratum`, `n`, `coef`, `fallback_level`.

**HAR-02 [REQ] · Calibration period**

- Given the overlap period,
- then the MODIS ↔ VIIRS calibration uses **only standard data** from MODIS and VIIRS S-NPP, from 2012-01-20 to the last
  standard S-NPP date (at most 2026-11-02), excluding NRT, NOAA-21 and months affected by GAP-03, GAP-04 or TYPE.
  Standard NOAA-20 is used only for the bridge between VIIRS sensors (SRC-02).
- _Verification:_ assertion in the flow and a test.
- _Source:_ README, GUIDE §7.2.4, S-NPP end notice (DATA_SOURCES §1.1).

**HAR-03 [REQ] · Leave-one-year-out cross-validation**

- Given a calibration,
- when it is validated leaving one year out each time,
- then |relative bias| ≤ 10 % and Spearman of the monthly seasonality ≥ 0.8 in at least 80 % of the strata with data.
  If this is not met, the dataset is **not published**.
- _Verification:_ `validation_<version>.json`; the flow returns an error code.
- _Source:_ AGENTS §10.3.

**HAR-04 [REQ] · No jumps in 2012**

- Given the harmonized series of a test region,
- when calibrated MODIS ("VIIRS equivalent") is compared with observed VIIRS in 2012–2014,
- then the mean monthly difference is ≤ 10 %.
- _Verification:_ integration test with a regional fixture.

**HAR-05 [REQ] · Reproducibility**

- Given the same inputs and the same configuration,
- when the pipeline runs twice,
- then the hash of `harmonized_cell_day` is identical.
- _Verification:_ reproducibility test (fixed seeds, deterministic ordering).

**HAR-06 [REC] · External validation**

- Given **MCD64A1** burned area,
- then the report includes the monthly correlation between harmonized activity and burned area per stratum.
- _Source:_ GUIDE §8.3.9 (there is no constant relation between pixel and burned area: it is used only for validation, not as a conversion).

---

## 10. QA, outputs and traceability (OUT)

**OUT-01 [REQ] · No row is lost without a record**

- Given a run,
- then `rows_read = rows_accepted + Σ rows_rejected(qa_reason)` per file.
- _Verification:_ balance test on the QA report.
- _Source:_ AGENTS §2.3.

**OUT-02 [REQ] · QA report**

- Given a run,
- then `data/reports/qa_<run_id>.json` contains: rows per file, rejections per `qa_reason`, coverage per satellite,
  gap days (known and detected), suspicious days, `type = 0` captured by the mask and the percentage of `low_confidence`.
- _Verification:_ validation of the JSON against `qa_report.schema.json`.

**OUT-03 [REQ] · Schema error threshold**

- If `schema_invalid / rows_read > 1 %` in any file, then the flow fails.
- _Verification:_ test.

**OUT-04 [REQ] · Dataset version**

- Given a published dataset,
- then `dataset_versions` records `nina_version`, the date, the configuration hash, the HAR-03 and TYPE-04 metrics,
  and the versions of each auxiliary dataset.
- _Verification:_ query to the table and test.

**OUT-05 [REQ] · Citation and legal notice**

- Given any exportable artifact,
- then it comes with the FIRMS citation, the **DOIs of the products used** (DATA_SOURCES §1.6) and the warning that the data
  are not suitable for tactical or local-scale decisions.
- _Verification:_ export test.
- _Source:_ README.

---

## 11. Auxiliary data (AUX)

**AUX-01 [REQ] · Source registry**

- Given `data/sources.yaml`,
- then each source has: `name`, `url`, `version`/`collection`, `license`, `download_date`, `sha256` and `used_in` (criteria that use it).
  URLs come from `docs/DATA_SOURCES.md`, and every URL marked ⚠️ is verified with a real request before use.

**AUX-02 [REQ] · Licenses compatible with the use**

- Given an auxiliary dataset with a restrictive license (e.g. **GADM: free only for academic and non-commercial use**),
- when the app is going to be published or used commercially,
- then the decision is documented in an ADR, or it is replaced by an openly licensed source.
- _Verification:_ the `license` field is in `sources.yaml` and the corresponding ADR exists.

**AUX-03 [REQ] · Caution with MCD12Q1 from 2021**

- Given the urban mask based on MCD12Q1 v6.1,
- when years from 2021 onwards are used,
- then the last year before 2021 is used or it is replaced by GHSL, and the choice is recorded in `sources.yaml`.
- _Verification:_ configuration review and a loading test.
- _Source:_ MCD12Q1 v6.1 metadata (the training data were not updated; the producer asks for caution from 2021).

| Data                                                                   | Required | Used in                |
| ---------------------------------------------------------------------- | -------- | ---------------------- |
| FIRMS MODIS C6.1 standard + NRT                                        | Yes      | everything             |
| FIRMS VIIRS S-NPP standard (2012-01-20 → 2026-11-02)                   | Yes      | HAR, TYPE-04, SRC-02   |
| FIRMS VIIRS NOAA-20 standard + NRT (2018 →) and NOAA-21 NRT (2024 →)   | Yes      | SRC-01, SRC-02, NRT    |
| FIRMS `data_availability` and `missing_data`                           | Yes      | ING-09, GAP-06         |
| Global daily counts per satellite (monthly MCD14ML or global FIRMS)    | Yes      | ING-07, GAP-02         |
| Administrative boundaries (GADM / INEI)                                | Yes      | API, HAR-01 (fallback) |
| Biomes or ecoregions (RESOLVE 2017)                                    | Yes      | HAR-01                 |
| MCD12Q1 C6.1 (urban class) or GHSL                                     | Yes      | TYPE-02, TYPE-05       |
| Holocene volcanoes (Smithsonian GVP)                                   | Yes      | TYPE-02                |
| Land/water mask                                                        | Yes      | TYPE-02                |
| MOD14CMQ / MYD14CMQ (0.25°, monthly)                                   | No       | GAP-05                 |
| MCD64A1 (burned area)                                                  | No       | HAR-06                 |
| IANA time zones (timezone-boundary-builder)                            | No       | local date in the API  |

---

## 12. Sensor continuity and acquisition (SRC)

**SRC-01 [REQ] · VIIRS series without S-NPP from 2 Nov 2026**

- Given that S-NPP stopped delivering new data on **2026-11-02 at 13:00 UTC**,
- when the VIIRS series after that date is built,
- then NOAA-20 is used (and NOAA-21 as a continuity backup). The NRT job does **not** query `VIIRS_SNPP_NRT`, and a
  configuration that includes it fails validation.
- _Verification:_ test of the NRT job configuration; assertion in `nrt_daily_flow`.
- _Source:_ NASA FIRMS and NESDIS notice about the end of S-NPP.

**SRC-02 [REQ] · Bridge between VIIRS sensors (S-NPP → NOAA-20)**

- Given the overlap of **standard** S-NPP and NOAA-20 data (2018 → 2026-11-02),
- when the "VIIRS equivalent" series is assembled,
- then an S-NPP ↔ NOAA-20 factor is estimated per stratum and month (same method as HAR-01 and HAR-03) and applied to NOAA-20 from
  2026-11-02, so that the satellite change does not produce a jump. It is validated with |relative bias| ≤ 5 % in the overlap.
- _Verification:_ `inter_viirs_bridge_<version>.json` + continuity test in November 2026.
- _Source:_ NASA states that NOAA-20 and NOAA-21 carry the same VIIRS in the same orbital plane, about 50 minutes apart.
  The different overpass time justifies checking the bias rather than assuming it is zero.

**SRC-03 [REQ] · MODIS without a fixed end**

- Given that NASA recommends migrating away from MODIS and that Terra is the only morning overpass,
- when Terra or Aqua stop delivering data,
- then the pipeline keeps working: the harmonized series is anchored on VIIRS (MODIS is only used, calibrated, for
  2000–2011), GAP-07 is applied and the end is recorded in `sensor_lifecycle.yaml`.
- _Verification:_ test simulating the end of Terra and then of Aqua; the 2012 → today series does not change.

**SRC-04 [REQ] · FIRMS API limits**

- Given the API client (`nina/io/firms_api.py`),
- then it respects **5000 transactions every 10 minutes per MAP_KEY** (counting each day of `DAY_RANGE` as one transaction),
  uses `FIRMS_MAX_DAY_RANGE` (configurable, default 5), retries with exponential backoff on 429 and 5xx errors, and records usage
  by querying the MAP_KEY status.
- _Verification:_ test with a simulated server that returns 429; the computed number of transactions matches the recorded one.

**SRC-05 [REQ] · RT and URT data**

- Given that FIRMS removes RT and URT detections when it processes the corresponding NRT data, or after 6 h,
- when the NRT job runs,
- then only NRT data older than 6 h are ingested as final. RT and URT detections, if used, are stored as
  `quality_level = "rt"`, marked `is_provisional` and replaced in the next run.
- _Verification:_ test replacing RT with NRT.

**SRC-06 [REQ] · Availability and delay of standard data**

- Given `/api/data_availability`,
- when deciding which period is provisional and what to reprocess,
- then `is_provisional` is computed from the real last standard date of each sensor, not with a fixed number of days. FIRMS
  states a delay of about 3 months (Readme) or about 5 months (download page), so `PROVISIONAL_DAYS` only serves as a fallback
  (default 150). A weekly job replaces NRT with standard data when they appear.
- _Verification:_ test with simulated availability dates.

**SRC-07 [REQ] · Credentials**

- Given `FIRMS_MAP_KEY` and Earthdata Login,
- then they are read from environment variables or from `~/.netrc`, never appear in logs, reports or commits, and CI uses _secrets_.
- _Verification:_ test that searches for key patterns (32 hexadecimal characters) in the logs; _secret scanning_ in CI.

**ING-08 [REQ] · Documented acquisition strategy**

- Given the pipeline,
- then the history is loaded from the archive download tool or the country summaries, recent data from the API, and
  keyless NRT files only as a backup, according to the table in DATA_SOURCES §3. The API is not used to download whole years day by day
  when the archive download exists.
- _Verification:_ review of `scripts/` and `nina/` and the run's transaction report.

**ING-09 [REQ] · Sensors and dates taken from the API**

- Given the start of each run,
- then the pipeline queries `data_availability` and stores the response in `data/interim/data_availability_<run_id>.csv`.
  Coverage (TMP-03), standard or NRT quality (ING-04) and reprocessing (SRC-06) are based on that file.
- _Verification:_ the file exists and the report references it.

---

## Acceptance report template

`data/reports/acceptance_<run_id>.md`

```markdown
# Acceptance report · run <run_id> · nina <version>

| ID      | Status         | Evidence                                                       | Notes                                          |
| ------- | -------------- | -------------------------------------------------------------- | ---------------------------------------------- |
| ING-01  | met            | tests/test_ingest.py::test_ingest_detects_source_from_filename |                                                |
| GAP-01  | met            | known_gaps.yaml (commit abc123)                                |                                                |
| GAP-05  | pending        | —                                                              | MOD14CMQ 2001–2024 still to be downloaded      |
| TYPE-04 | not met        | static_mask_validation_0.3.0.json                              | recall 0.74 < 0.80 → adjust volcano radius     |
| ...     |                |                                                                |                                                |

Result: ✅ ready to publish / ❌ not ready (list of unmet [REQ] criteria)
```

**Final rule:** the agent **cannot** publish a dataset or mark the task as done if any **[REQ]** criterion
remains `not met` or without evidence.
