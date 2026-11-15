# ADR 0005 · Audit fixes: method 0.4.0

Date: 2026-11-14 · Status: accepted · Supersedes parts of ADR 0002 and ADR 0003

## Context

An independent code audit of method 0.3.0 (product `95506369dcd7a7768aebfcd3`) recomputed all coefficients and
confirmed the arithmetic, but found rules that served wrong or misleading numbers:

1. Days without valid S-NPP data were neither filled nor flagged, yet the month kept a value, an anomaly and a place
   in the baseline. Peru, July 2022 was served as −16 % against its median; filling the five missing days gives about
   +14 %. Partial S-NPP outages (a few percent of normal coverage) went undetected.
2. Country outlines crossing the antimeridian (Russia/Chukotka, Fiji) were read as bands around the globe: Alaskan
   fires counted as Russia, Australian fires as Fiji. The 1:110m coastline also left coastal land cells unassigned.
3. The validation gates pool bias over all years. With a ratio-of-totals estimator, summed leave-one-year-out
   predictions reproduce the total almost by construction, so the gate cannot see per-year error.
4. A single unvalidated cell-day nulled a whole month: 35 of 113 pre-2012 months for Peru, for 0.11 % of activity.
5. The FIRMS readme entry "some missing data from mid August 2007" was applied as a hard gap to 15–31 August 2007,
   although daily counts are normal. The same applied to 2001-07-04/05 and 2009-04-22.
6. The current year could never get an anomaly, which is the main question of the challenge
   ("compare the current month against the historical median").
7. Terra-only months (November 2000 → July 2002) have country-year errors of −40 % to +38 % out of sample.

## Decision

Method version **0.4.0**. Thresholds of the publication gates are unchanged.

| # | Change | Where |
|---|---|---|
| 1 | In the S-NPP era a country-day uses NOAA-20 through the validated bridge when S-NPP is not valid, or when S-NPP sees fewer than 40 % of the cells NOAA-20 saw that day in that country (with ≥ 50 NOAA-20 cells). The day is marked `snpp_filled`; the calendar reports `noaa20_filled_days`. A month with any day still missing gets no comparable value and no anomaly; `observed_activity` keeps the partial sum. | `product.build_support`, `nina/harmonized.py` |
| 2 | Polygon parts wider than 180° are cut at ±180° (polar parts excluded). Cell centres outside every outline are snapped to the nearest country within 0.25°. `COUNTRY_METHOD = 2` is part of the geography cache signature; a cached grid only has its countries recomputed. | `geography.py`, `nina/harmonized.py` |
| 3 | Validation also reports, per stratum, the relative bias of each held-out year, its median and 90th percentile, the share of years within ±10 %, and the Spearman of uncalibrated MODIS. The same summary is given for all passing strata. | `calibration.validate_years` |
| 4 | A month keeps its value when at most 1 % of its observed cell-days lacks a validated coefficient. The value is the validated sum and `unvalidated_share` is reported. | `nina/harmonized.py` |
| 5 | Readme gaps are candidates: a listed day is a gap only if the platform's global count falls below 50 % of its 31-day rolling median. Otherwise the day stays valid with reason `known_gap_unconfirmed`. The Aqua FMU failure (August–September 2020) stays forced. | `coverage.daily_quality`, `model.quality_table` |
| 6 | Every complete month gets an anomaly against the same calendar month of all *other* eligible years (complete, standard quality, declared archive, before the snapshot year). The current year is compared but never enters the baseline. The response adds the p10–p90 band and the rank. A month in progress gets `month_to_date`: day 1 to the last fully supported day, compared with the same days of the other eligible years, with no anomaly below 8 days. | `nina/harmonized.py` |
| 7 | Terra-only coefficients are not served; the series starts in July 2002 and the climatology in 2002. | `product.SERVED_SAMPLINGS`, `nina/harmonized.py` |

Also: free-drawn polygons drop countries holding less than 2 % of the selected cells (border slivers of the generalized
outlines would otherwise require a neighbour's archive and blank the history). The activity table is built year by year,
because `count(DISTINCT)` does not spill to disk and ran out of memory on the full archive.

## Consequences

- Numbers change for months with S-NPP outages (now filled from 2018 onward), for August 2007, for countries near the
  antimeridian and for coastal cells. Peru's country assignment is unchanged.
- With the corrected geography, the NOAA-20 bridge passes its gate (80.5 % of strata; two small "unclassified biome"
  strata in Brazil and Indonesia changed). The MODIS gates and the mask still fail.
- Before April 2018 there is no NOAA-20; S-NPP outage days remain gaps and those months have no comparable value.
- Year-to-year error stays about ±10 % in the MODIS era (median ≈ 6 % in passing strata). Close rankings of MODIS-era
  years should not be over-interpreted; the documentation says so.
- Not changed: the ratio-of-totals model (the ratio depends on activity level, a log-log slope of about 0.74–0.89),
  the persistence mask pooling all VIIRS platforms, and NRT months having no `type` field. They are recorded as known
  limitations in `docs/BACKEND_STATUS.md`.
