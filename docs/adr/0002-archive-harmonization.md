# ADR 0002: harmonization of observed activity and gated publication

Status: implemented and under evaluation. Method version: **0.2.0** (extended in ADR 0003).

## Problem

MODIS and VIIRS pixel counts are not the same unit. The Peruvian count prototype is not a global validation. The
interface is built by another developer; this change delivers processing, a contract and evidence.

## Decision

The base unit is an H3 resolution-7 cell on a UTC day with activity. Several detections from one overpass, or from
Terra and Aqua, in the same cell and day do not increase that unit. Provenance and the real pixel area are kept as QA
attributes.

Low confidence, non-vegetation types and static sources are filtered out, using persistence at resolution 8, GHSL,
GVP and a land/water mask. The filters are audited before calibration; the original observation archive stays intact.

Persistence is built from nominal/high VIIRS detections during the overlap: the MODIS types used as the validation
reference do not build their own mask. Before VIIRS, MODIS persistence is used as a retrospective approximation, and
that limit is recorded. False removals and recovery are evaluated only over the standard-quality overlap with S-NPP.

The coefficients map activity to a VIIRS S-NPP-equivalent scale. An equivalent unit can be fractional or larger than one
observed unit: it is an aggregate adjustment, not a probability or a new fire location. No individual detections are
invented. Calibrated values are exported as weighted aggregates/cells, separate from the original points.

Strata are biome/ecoregion × calendar month × sampling regime (Terra only, or Terra+Aqua). When a stratum lacks support,
a higher level is evaluated and the fallback is recorded. Only standard processing is used for fitting. NOAA-20 needs its
own bridge to S-NPP; NOAA-21 is not treated as equivalent by default.

The fit is a ratio of totals, equivalent to a Poisson model with an offset, over months where source activity is above
zero. Months without source signal cannot estimate that offset: they are excluded from the fit but kept in the
validation, and their error is recorded. Country and biome are assigned from the centre of the analysis cell; masks use
the centre of their sub-cell. **Strata that fail the evaluation abstain when the product is served.**

The historical archives of five countries provide enough years to separate training, selection and evaluation.
Evaluation uses reserved years and leave-one-year-out validation; the recent global archive is used to review geographic
transfer. A coefficient is not declared valid outside the evaluated domain.

Gaps and days with insufficient support remain missing data. Global daily counts, or those of a broad sample, reveal
likely outages, but they do not reconstruct cloud cover or local L2 observation opportunities. Archive zeros, where
justified, still do not prove the physical absence of fire.

## Publication gates

The repository's acceptance thresholds are kept: absolute relative bias ≤ 10 % and Spearman ≥ 0.8 in at least 80 % of
evaluable strata, and bias ≤ 5 % for the VIIRS bridge. The static mask must recover ≥ 80 % of the reference MODIS static
sources and remove ≤ 2 % of `type=0` detections.

If evidence is missing or a mandatory gate fails, the result stays a candidate and the API reports that there is no
publishable product. A scientific failure is not turned into a success by changing a threshold after seeing the test.
The report gives errors by year and stratum, in addition to the global metric.

## Limits

The product describes detected activity under an identified archive support. It does not estimate burned area,
individual fires, causes or spread. Correcting for L2 observation opportunities and validating against burned area are
explicit extensions. Recent NRT data are marked provisional and do not train the model.
