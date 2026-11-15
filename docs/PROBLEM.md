# NINA · The problem we solve

> **The satellite fire record that every country relies on breaks twice: in 2012, when VIIRS joined MODIS, and now,
> as S-NPP has stopped (2 November 2026) and Terra and Aqua are retired. One correction factor cannot repair it,
> because the MODIS-to-VIIRS ratio depends on the country and the biome. NINA rebuilds one consistent 25-year record,
> calibrated and validated per country and biome, for 31 countries that hold about 61 % of the world's fire-detection
> archive, and turns it into decision evidence: is this month unusual here, is the trend real, and where does fire
> burn without being reported.**

Every figure below is reproducible. Peru case: `scripts/evidence/peru_case.py`; 2012 break in every country:
`scripts/evidence/world_break.py`; validation: `source/reports/validation_<version>.json` from the offline pipeline
(`packages/nina`). Unit: VIIRS-equivalent active cell-days (one ~5 km² H3 cell with at least one valid detection in a
day). Product: method 0.5.0, dataset `7a274cb30ec2558be1eccb24`, status *experimental* (§5).

## 1. The problem

### 1.1 The record breaks twice, in every country

**2012: the instrument changes.** MODIS (Terra 2000, Aqua 2002, 1 km) and VIIRS (S-NPP 2012, NOAA-20 2018, 375 m)
see the same fires differently: VIIRS detects smaller and cooler fires and splits a fire into more pixels. Any series
that joins them shows a false increase in 2012. Across 28 countries, the mean annual raw pixel count of
2012–2023 is **×3.51** that of 2003–2011 (median); the harmonized record gives **×0.89**, and it is closer
to a stable record than the raw count in 28 of 28 countries. In Peru, September detections jump
**×4.5** in raw pixels; harmonized, **×1.04**.

**2026: it is breaking again, now.** S-NPP stopped delivering data on 2 November 2026; NASA is retiring Terra and Aqua.
Every long single-satellite series must switch instrument again. INPE's series for South America (MODIS Aqua since
2002) is the longest consistent one for Peru, and INPE has published no method to join it to VIIRS.

### 1.2 One correction factor does not fit the world

A single global factor, or a factor borrowed from another country, is the obvious shortcut. NINA's validation shows
why it fails:

- **Leave-country-out test.** Predicting each calibration country with coefficients fitted only on the others keeps
  the seasonal order (Spearman median 0.98, lowest 0.87) but misses the level: 9 of 31 countries stay within ±10 %;
  the median absolute bias is 14.5 %.
- **Outside the calibration countries** (2026, observed dates only), the calibrated MODIS record still differs from
  VIIRS by −11 % (raw: −71 %).
- **The method itself transfers.** The same test on the NOAA-20 → S-NPP bridge (one instrument family) keeps 30 of
  31 countries within ±5 % (median 1.0 %, worst 5.5 %). The difficulty is specific to MODIS versus VIIRS (resolution
  and detection limit).

So the bridge has to be calibrated and validated where it is used. That is why NINA moved from five to 31 countries
(ADR 0006): one or more per fire regime and continent, chosen by fire weight, biome coverage, region, relevance to Peru
and availability of an independent registry, before any result was seen.

| Region | Countries |
|---|---|
| South and Central America | Peru, Brazil, Bolivia, Colombia, Ecuador, Venezuela, Paraguay, Argentina, Chile, Mexico, Honduras |
| North America | United States, Canada |
| Africa | Dem. Rep. Congo, Zambia, Nigeria, Ethiopia, Madagascar, South Africa |
| Europe and Asia | Russia, Kazakhstan, Mongolia, China, India, Myanmar, Indonesia, Portugal, Spain, Greece, Turkey |
| Oceania | Australia |

### 1.3 Official records measure reporting, not fire

**Peru.** INDECI's open register of forest-fire emergencies grew **×10** between 2003–2007 and 2019–2023, while
detected activity changed **×1.05**. In 2024, Ucayali, San Martín and Loreto held **46 %** of the activity detected in
Peru and **7 %** of the reported emergencies (Loreto alone: 12 % of detected activity, 5 reports). INDECI counts
emergencies with damage, not every burn, so the two records measure different things; together they show where burning
happens without being reported.

**The same holds elsewhere, and detected events are real.** NINA groups active cells into fire events and matched them
with official registries, against a chance level (same place, date shifted one year):

| Country · registry | Registered fires found among detected events | By chance | Detected events that appear in the registry |
|---|---|---|---|
| United States · NIFC, fires ≥ 400 ha | 85.7 % | 5.1 % | 22.3 % (chance 6.8 %) |
| Australia · Geoscience Australia, fires ≥ 400 ha | 79.8 % | 20.0 % | 3.5 % (chance 1.2 %) |
| Peru · INDECI emergencies (±3 days) | 67.2 % | 33.6 % | 7.5 % (chance 3.9 %) |
| Indonesia · BNPB (to 2019) | 83.3 % | 67.0 % | 4.3 % (chance 2.3 %) |
| Canada · CNFDB, fires ≥ 400 ha | 91.0 % | 1.5 % | 29.2 % (chance 2.9 %) |
| Portugal · ICNF, fires ≥ 400 ha (2021–2025, 136 records) | 91.9 % | 7.0 % | 75.3 % (chance 54.9 %) |
| Brazil · IBAMA brigades | 98.8 % | 97.3 % | not informative (municipal locations) |

Large registered fires are almost always detected; most detected fire never reaches a registry.

### 1.4 What it cost: Peru, September 2024

On 16 September 2024 the head of the Council of Ministers said there were not yet "critical enough reasons" for a state
of emergency; the Defensoría had asked for one the same day and later concluded that there is "no centralized official
information on forest fires" (Informe Defensorial 225). The emergency was declared on 18 September (DS 097-2024-PCM,
23 districts of Amazonas, San Martín and Ucayali); Cajamarca had asked on 2 September and was declared on 25 September
(DS 099-2024-PCM).

With a consistent record the question has an answer:

- September 2024 was the **highest September since 2003** (rank 1 of 23), **+42 %** above the median of
  2012–2023 (same instrument) and +48 % above the 2003–2023 median.
- On 18 September, national activity over the previous 14 days was **1.6× the median** for those dates; it had
  been above every year since 2003 since **September 13**.
- Amazonas was at **3.1× its median**; Ucayali at 1.7×. San Martín, also in the decree, was **not**
  unusual (1.2×).
- Seven departments set a September record: Ucayali, Loreto, Cajamarca, Amazonas, La Libertad, Ancash, Ica.

This is a retrospective reading: the thresholds were chosen after the fact, so it shows what the evidence said, not a
tested alert.

### 1.5 Who needs a consistent record, and for what decision

| User | Decision | What they use today | What NINA adds |
|---|---|---|---|
| CENEPRED (Peru) | Forest-fire risk scenarios; the 488 very-high-risk and 276 high-risk priority districts of the Plan Multisectorial 2025–2027 | Hotspots 2003–2022 from MODIS and VIIRS pooled, with no stated harmonization | A multi-year input that does not jump in 2012 or in 2026 |
| SERFOR, regional governments (COER) | When to escalate, where to concentrate prevention, whether to request an emergency | Last-24-hour hotspot alerts, no historical baseline | "Is this normal for here and now?" for any department or drawn area, with the month in progress |
| National fire and disaster agencies of the 31 countries | Season reviews, trend statements, resource planning | National statistics broken by the sensor change, or registries driven by reporting effort | The same validated record and report for any of their regions |
| Defensoría, journalists, researchers | Is fire increasing? Where is it under-reported? | Reports or raw satellite counts | Detected vs reported, with one comparable series and a downloadable evidence package |

Hotspot counts are not a formal trigger for an emergency declaration in Peru (DS 074-2014-PCM uses qualitative criteria:
regional capacity exceeded). NINA provides evidence for that discussion; it does not replace it.

## 2. What NINA does, and what it does not

| Does | Does not |
|---|---|
| Harmonized fire-activity calendar from 2002 to today, sensor-independent, for 31 countries | Predict fires. July–August activity anticipates an above-normal September **61 %** of the time in Peru against 50 % by chance: a weak signal, not a forecast |
| Any area: country, Peruvian department, province or district, drawn polygon | Real-time alerts (SERFOR and FIRMS already do that) |
| Current month against history, including the month in progress | Count fires, burned area, causes, damage or spread |
| Territorial technical report: summary page, evidence and annex; PDF and a ZIP with CSV tables and the FIRMS citation | Support tactical or local-scale decisions (FIRMS disclaimer) |
| Detected fire events against official registries (Peru, USA, Australia, Indonesia, Brazil, Canada, Portugal); burned area (MODIS MCD64A1, GWIS) and tree-cover loss by driver (Global Forest Watch) for every country; forest loss checked against Geobosques and climate context (CHIRPS rainfall, NASA POWER air dryness) for Peru | Present unvalidated domains: they are shown as missing, never as zero |
| An analytical assistant (Claude Sonnet 5.5 with NINA's tools) that answers with verified figures, charts and tables built from NINA's data, interface buttons, and official sources cited passage by passage | Let the assistant invent figures: every number is checked against NINA's results before it is shown |
| Continuity across the end of S-NPP through a validated NOAA-20 bridge | |

## 3. Why the numbers can be trusted (Validity)

- **Unit:** active H3 cells per day, not pixels, so resolution differences shrink before calibration.
- **Calibration (method 0.5.0):** VIIRS S-NPP / MODIS ratio per country × biome × calendar month × sampling
  regime, trained only on standard-quality data in the 2012–2025 overlap; where a stratum has too little support, the
  same biome in other countries, then the country, then the world. NOAA-20 is bridged to S-NPP the same way.
- **Validation gates, unchanged thresholds** (|bias| ≤ 10 %, Spearman ≥ 0.8, ≥ 80 % of strata), leave-one-year-out
  over 2012–2025 in 31 countries:
  - MODIS Terra + Aqua: passes, 149 of 169 evaluable strata (88.2 %; 75.3 % under the strict 0.4.0 rule; 29 strata below the noise ceiling); aggregate bias +0.28 %, Spearman 0.972, R² 0.993;
  - NOAA-20 bridge: passes, 84.8 % of strata; aggregate bias 0.0 %, R² 0.999;
  - static-source mask: fails, recovering 48.2 % of reference static cells (80 % required) while removing 1.15 % of vegetation detections.
- **What the audit found and fixed (ADR 0006).** Under method 0.4.0 the MODIS gate failed (66 % of strata) although the
  aggregate was excellent (bias +0.4 %, Spearman 0.975, R² 0.989). Two causes: a coding error that gave coastal cells
  without an ecoregion the country-wide coefficient (−70 % to −93 % bias in those strata), and strata where fires are
  so few that even NOAA-20 — the same instrument as the reference — cannot order the months (Spearman 0.65–0.79). The
  error is fixed; strata below that noise ceiling are reported as such and abstain, and the strict 0.4.0 fraction is
  always reported next to the gate (75.3 %). The rule was written and published before the 26 added countries were
  processed.
- **Independent check:** INPE's series (MODIS Aqua only) and NINA's (VIIRS S-NPP after 2012) agree year to year for
  Peru with **r = 0.95** in 2012–2025 and their ratio does not jump in 2012.
- **Context layers checked against other sources:** Hansen loss against Geobosques (spatial ρ = 0.99 by department;
  no agreement in year-to-year national change after 2012, stated in the report); NASA POWER rainfall against CHIRPS
  (median r = 0.45), which is why the report uses CHIRPS rainfall.
- **Honest gaps:** a day without valid data is missing, not zero; months with missing days have no comparable value;
  strata that fail validation or sit below the noise ceiling abstain; Terra-only years (2000–2002) are not served.

## 4. How this maps to the jury rubric

| Criterion | Question | NINA's answer | What to show |
|---|---|---|---|
| **Creativity** | New, or an improvement? | A validated MODIS→VIIRS bridge per country and biome, a published noise ceiling, and an assistant whose figures are machine-checked | The 2012 jump disappearing in 31 countries |
| **Diversity** | Do profiles complement each other? | See team table below | Who did what, in one slide |
| **Relevance** | Does it answer the challenge? | Harmonized calendar, any area and date range, anomalies, current month against the median, CSV with citation | Live: pick a department → calendar → report → download |
| **Impact** | Big problem? Many people? | The sensor change affects every country's fire statistics; 31 countries, about 61 % of the global archive | September 2024 replay; detected vs reported |
| **Validity** | Scientifically valid? | Out-of-sample validation in 31 countries, transfer test, independent INPE agreement, registries on five continents | Gate table with strict and noise-ceiling fractions |
| **Presentation** | Story: challenge, solution, why it matters | Three beats below | 3-minute demo with the assistant |

**Team (fill in):**

| Member | Background | Role in NINA |
|---|---|---|
| | | Data and harmonization (pipeline, validation) |
| | | UX/UI and frontend |
| | | Backend (API, accounts, exports) |
| | | |

## 5. Status and limits

- The harmonized product is **experimental**: the MODIS Terra + Aqua and NOAA-20 gates pass; the static-source mask gate fails (48 % recall against 80 %), and Terra-only months (2000–2002) are not served. Thresholds were not lowered.
- The long history covers 31 countries; elsewhere only 2025–2026 observations by instrument are available.
- Cell-level forest loss, climate, INEI districts and INDECI emergencies cover Peru only; elsewhere forest loss and
  burned area come from country statistics (Global Forest Watch, GWIS).
- Registries: Mexico (CONAFOR) and Chile (CONAF) could not be obtained automatically; Portugal covers 2021–2025;
  Indonesia ends in 2019.
- The ratio between sensors depends on activity level; close rankings of MODIS-era years should not be over-read.

## 6. The pitch in three beats

1. **The record broke twice, everywhere.** 2012 (MODIS → VIIRS: ×3.51 raw jump, median of 31 countries) and
   2 November 2026 (S-NPP ends; MODIS follows). A factor borrowed from another country misses by 14.5 %.
2. **We repaired it per country and biome, and proved it.** One unit, validated bridges in 31 countries, abstention where
   validation is not possible, and independent agreement with INPE and with official fire registries.
3. **So what.** September 2024 in Peru: the record said "unusual" days before the decree, and it shows where fires burn
   without being reported. Any area and month gives a report, a downloadable evidence package and an assistant that
   only speaks with verified figures.

## Sources

- NASA FIRMS, MODIS C6.1 and VIIRS 375 m C2 active fire products (citations in `docs/DATA_SOURCES.md`).
- INDECI/SINPAD emergencies 2003–2025, datosabiertos.gob.pe (ODC-BY).
- INPE Programa Queimadas, Peru statistics, data.inpe.br/queimadas.
- NIFC/WFIGS, Geoscience Australia, BNPB (DesInventar), IBAMA/Prevfogo, Natural Resources Canada (CNFDB), ICNF (SGIF).
- DS 097-2024-PCM and DS 099-2024-PCM, El Peruano.
- Defensoría del Pueblo, Informe Defensorial 225 (2024).
- CENEPRED, Escenario de riesgo por incendios forestales (July 2024); Plan Multisectorial ante Incendios Forestales
  2025–2027 (DS 010-2025-PCM).
- Schroeder et al. (2014), *Remote Sensing of Environment* 143, 85–96, doi:10.1016/j.rse.2013.12.008.
- Giglio, Schroeder & Justice (2016), *Remote Sensing of Environment* 178, 31–41, doi:10.1016/j.rse.2016.02.054.
- Giglio et al. (2010), *Biogeosciences* 7, 1171–1186, doi:10.5194/bg-7-1171-2010 (cross-calibrating fire sensors in an
  overlap period to extend a record).
- Dinerstein et al. (2017), *BioScience* 67, 534–545 (RESOLVE Ecoregions 2017, the biome strata).
