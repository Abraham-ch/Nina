# NINA · Backend and data delivery

Status on 14 November 2026. Method `0.4.0`; candidate `e9f9a7a7a47bd640f9d27999`. What problem this serves: [PROBLEM.md](PROBLEM.md).

**Global exploration works, and the new backend can be tried as a local experimental demo. The harmonization has not yet
passed its scientific gates.** The existing interface still queries observations. Wiring the visual interface to the
harmonized product is the UX/UI developer's task.

## Delivered scope

| Component | Result |
|---|---|
| Observed base | 59,440,077 unique observations, with the existing map, calendar and download features. |
| World | Real 2025–2026 windows, different for each product. Not a complete global history since 2000. |
| Extended history | 240 yearly archives for Brazil, Australia, Indonesia, the United States and Peru: MODIS 2000–2025, S-NPP 2012–2025 and NOAA-20 2018–2025, as available. Authorized download completed. |
| Harmonized backend | World/country/polygon selection, monthly calendar, H3 cell centres for the map, CSV, full ZIP, provenance and an evidence-based assistant. |
| Integration | [Contract](HARMONIZED_CONTRACT.md), [OpenAPI](../openapi.json) and [generated TypeScript types](../openapi.d.ts). |

The 240 yearly originals add up to **7.70 GB** (decimal) and the team's nine global originals to **23.54 GB**, excluding
derivatives, databases and caches. The five auxiliary sources provide biomes, urban centres, coast/water, volcanoes and
countries; their licences, versions and hashes are recorded locally.

The run read **155,263,896 rows**: 155,263,626 were accepted before deduplication, 270 were rejected with recorded reasons
and 2,824,866 duplicates were removed. That left **152,438,760 normalized rows** and **62,437,190
cell/day/platform/quality activity rows before merging**. These totals are not individual fires.

## How the data are processed

`packages/nina` normalizes, deduplicates, gives standard data precedence over NRT within each spatial scope, applies the
filters and counts daily presence on H3 resolution 7. The mask uses resolution 8. Repeated detections in one cell and day
do not become additional fires.

S-NPP is the observed reference during its available period. MODIS is adjusted with the overlap years and NOAA-20 has an
independent continuity evaluation. Only standard data are used for calibration. Estimates in domains without validation
are left as `null`; NRT data keep their provisional status.

The API reads the precomputed Parquet product, about **200 MB**, through DuckDB. It does not recalibrate sensors at query
time. The Python 3.12 scientific environment in `packages/nina/` and the Python 3.14 server environment are independent
([ADR 0004](adr/0004-offline-harmonization-pipeline.md)). The local demo does not need PostGIS, Redis or MinIO.

The unit is **VIIRS-equivalent activity per cell and day**. It does not measure burned hectares, distinct fires, cause,
future risk or spread. Points in the harmonized product are cell centres with aggregated weights, not new satellite
detections.

## Try it

From the repository root:

```powershell
.\start-nina.ps1
```

Application: <http://127.0.0.1:8000>. Interactive API docs: <http://127.0.0.1:8000/docs>. Availability:
`GET /api/harmonization`.

Set `NINA_EXPERIMENTAL_HARMONIZATION=true` in your local `.env` to query the draft; `.env.example` keeps it off. The
draft lives in `source/review/`. **There is no `source/harmonized/current.json`: scientific publication stays blocked.**
Responses and downloads carry `validation_status=experimental` and `scientifically_validated=false`.

Two selections for `POST /api/harmonized/analyses`:

```json
{"country":"world","year_start":2025,"year_end":2026,"selected_year":2026,"selected_month":7}
```

```json
{"country":"Peru","year_start":2001,"year_end":2025,"selected_year":2025,"selected_month":9}
```

Peru, September 2024 (0.63 s): **20,909 units**, complete (one day filled from NOAA-20), against a median of 14,081 over
22 other eligible years: **+48.5 %, rank 1 of 23**. The ZIP's `cells.csv` sums to the same 20,909. October 2026
(provisional): +43.6 %, rank 3 of 25. November 2026 is in progress: `month_to_date` compares its 5 valid days with the same
days of 24 years (no anomaly below 8 days). The world, July 2026, has `observed_activity` 619,707 but no comparable value:
its NOAA-20-filled days fall in countries without a validated bridge (`unvalidated_domain`). These are single local
measurements, not a performance commitment.

The assistant explains results, archive support and limits using facts computed by the server. The analytical assistant
(`/api/analyst`, [ANALYST.md](ANALYST.md)) is deterministic by default; with `ANTHROPIC_API_KEY` configured, Claude plans
the tool calls and writes the answer, and an answer is shown only if each of its figures appears in the tool results.
No key is configured in this delivery.
Do not present this delivery as AI-based prediction.

## Pending scientific validation

A good average is not enough: at least 80 % of the evaluable country/biome strata must meet the bias and correlation
limits. 41 strata were evaluated with years held out of training.

| Gate | Measured result | Threshold | Status |
|---|---|---|---|
| Static mask | Recovers 43.72 % of reference cells (10,943 of 25,032); removes 1.18 % of vegetation rows | Recovery ≥ 80 % and removal ≤ 2 % | Fails |
| MODIS Terra only | 58.54 % of strata pass; aggregate bias +1.33 %; yearly error median 11 %, p90 34 % | ≥ 80 %; absolute bias ≤ 10 % and Spearman ≥ 0.8 | Fails (not served) |
| MODIS Terra+Aqua | 65.85 % of strata pass, holding 99.1 % of activity; aggregate bias +0.37 %; yearly error median 6.2 %, p90 20.5 %, 67 % of years within ±10 % | Same as above | Fails |
| NOAA-20 bridge | 80.49 % of strata pass, holding 99.96 % of activity; aggregate bias −0.01 %; yearly error median 2.0 %, p90 8.8 %, 91 % of years within ±10 % | ≥ 80 %; absolute bias ≤ 5 % and Spearman ≥ 0.8 | **Passes** |

The bridge passes in 0.4.0 because the coastal and antimeridian fixes changed two small "unclassified biome" strata
(Brazil and Indonesia); thresholds were not changed. Uncalibrated MODIS already passes the Spearman criterion in 28 of 41
strata, so that criterion says little on its own: the per-year error is the informative number.

A diagnostic outside the five historical countries gives **−33.85 % bias for MODIS Terra+Aqua in 2026** (−0.06 % for the NOAA-20 bridge). This calibration
must therefore not be extrapolated to the whole planet's history. The NOAA-20 bridge has near-zero aggregate bias in that
diagnostic, but that does not replace the per-stratum criterion.

The mask uses GHSL urban centres, not an exhaustive built-up raster. Its static-source catalogue learns MODIS labels from
periods before the evaluation. Widening neighbourhoods did not fix recovery and in some trials removed too much
vegetation; the diagnostics were kept without changing the thresholds.

Temporal support measures archive availability. Local cloud-free observation opportunities were not reconstructed and
authenticated L2 products were not processed automatically. Official outages of the US/Canada service stay within that
scope and are not applied to the rest of the planet.

To approve the harmonization: improve and independently evaluate the mask; review the failed strata and geographic
transfer; and complete the evidence for all mandatory criteria. Every method change needs an ADR, a version bump and
regeneration. Do not edit gates or lower thresholds to enable a publication.

## Audit and fixes in 0.4.0

An independent audit of 0.3.0 confirmed the arithmetic (all coefficients recomputed) and found rules that served wrong
numbers. They are fixed in 0.4.0 ([ADR 0005](adr/0005-audit-fixes-0.4.0.md)):

| Finding in 0.3.0 | Fix in 0.4.0 |
|---|---|
| S-NPP outage days were neither filled nor flagged (Peru, July 2022: −16 % served, about +14 % real) | NOAA-20 fills them through the validated bridge, also on partial outages; months still missing days get no value |
| Antimeridian outlines: Alaska counted as Russia, Australia partly as Fiji; coastal cells unassigned | Outlines cut at ±180°; coastal cells snapped within 0.25° |
| Gates pool bias over all years and cannot see per-year error | Per-year error and the uncalibrated baseline are reported per stratum |
| One unvalidated cell-day blanked a whole month (35 of 113 pre-2012 months in Peru) | Up to 1 % unvalidated cell-days: validated sum with `unvalidated_share` |
| False gap deleted 15–31 August 2007 | Readme gaps are confirmed with daily counts |
| The current year never got an anomaly | Every complete month is compared with all other eligible years; months in progress get `month_to_date` |
| Terra-only years (2000–2002) had ±40 % yearly error | Not served; series and climatology start in 2002 |

Known limitations that remain: the inter-sensor ratio depends on activity level (log-log slope 0.74–0.89, so very
active MODIS-era years may be overestimated by up to ~20 %); persistence for the static mask pools all VIIRS platforms;
NRT months lack the `type` field (+0.4 % globally, up to +22 % in some gas-flaring countries); after 2 November 2026 only
the five historical countries have a validated NOAA-20 bridge.

## Hand-over to UX/UI

1. Use `/api/harmonized/analyses` for the harmonized calendar. `/api/analyses` keeps observations, in a different unit.
2. Keep the same selection and `dataset_id` across calendar, map, assistant and downloads. Do not sum the map sample to
   compute totals.
3. Show the experimental status, unit, gaps, partial coverage and provisional status. `null` is not zero, and `complete`
   does not mean scientific approval.
4. Keep the FIRMS citation and the historical-context notice. Downloads already include provenance, version and limits.

## Evidence and reproduction

Data and reports are excluded from Git. A fresh clone must acquire and prepare the inputs; the commit does not
redistribute NASA data and contains no credentials.

| Local file | Evidence |
|---|---|
| `source/history-inputs.json` | 240 yearly archives and hashes. |
| `source/auxiliary-inputs.json` | Auxiliary sources, versions and licences. |
| `source/interim/observed_batch_coverage.json` | Real global windows. |
| `source/reports/qa_0.4.0.json` | Row reconciliation, rejections, coverage and gaps. |
| `source/reports/validation_0.4.0.json` | Validation by stratum and year. |
| `source/reports/static_mask_validation_0.4.0.json` | Mask evaluation. |
| `source/reports/acceptance_e9f9a7a7a47bd640f9d27999.md` | Passed, failed and pending-audit criteria. |
| `source/reports/tests-*.xml` | Software tests. |
| `source/reports/technical-checks.json` | Lint and types. |
| `data/reports/peru_evidence_e9f9a7a7a47bd640f9d27999.json` | Every figure of [PROBLEM.md](PROBLEM.md), from `scripts/evidence/peru_case.py`. |

**31 pipeline tests and 42 server tests pass**, including 9 for the harmonized contract. They verify the software and
do not turn failed scientific gates into passes. Criteria without audited evidence stay pending in the acceptance report.

Acquisition, processing and draft-building commands are in the [contract](HARMONIZED_CONTRACT.md) and in
[`packages/nina/README.md`](../packages/nina/README.md). The model and acceptance steps exit non-zero when the candidate is
not publishable; that is deliberate. In this workspace there is no need to download the 240 archives again.
