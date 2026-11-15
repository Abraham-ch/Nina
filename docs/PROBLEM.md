# NINA · The problem we solve

> **Peru's fire record is about to break, and the official one never could show a trend. NINA keeps one consistent
> 25-year record across satellites, so anyone can see whether this season is unusual, where, and where burning goes
> unreported.**

Every figure below is reproducible with `scripts/evidence/peru_case.py` (output in
`data/reports/peru_evidence_<dataset>.json`). Unit: VIIRS-equivalent active cell-days (one ~5 km² H3 cell with at least
one valid detection in a day). Product: method 0.4.0, dataset `e9f9a7a7a47bd640f9d27999`, status *experimental* (see §5).

## 1. The problem

### 1.1 Two records that cannot answer "is this normal?"

**The satellite record changes instrument.** MODIS (Terra 2000, Aqua 2002) and VIIRS (S-NPP 2012, NOAA-20 2018) see
the same fires differently: in Peru, September detections jump **×4.5** in raw pixels when VIIRS arrives
(2012–2023 against 2003–2011). Any series that simply joins them shows a false increase in 2012. After harmonization
the same comparison gives **×1.04**.

**It is breaking again, now.** S-NPP stopped delivering data on 2 November 2026. NASA has announced that Terra and Aqua
begin shutting down between late 2026 and early 2027. The longest single-satellite series for Peru, INPE's (MODIS
Aqua since 2002), will have to switch sensor; INPE has published no method to join the two.

**The official record of reported fires measures reporting, not fire.** INDECI's open register of forest-fire
emergencies grew **×10** between 2003–2007 and 2019–2023, while detected activity changed
**×1.05**. In 2024, Ucayali, San Martín and Loreto held **46 %** of the activity
detected in Peru and **7 %** of the reported emergencies (Loreto alone: 12 % of detected
activity, 5 reports). INDECI counts emergencies with damage, not every burn, so the two records
measure different things; together they show where burning happens without being reported.

### 1.2 What that cost in September 2024

On 16 September 2024 the head of the Council of Ministers said there were not yet "critical enough reasons" for a state
of emergency; the Defensoría had asked for one the same day and later concluded that there is "no centralized official
information on forest fires" (Informe Defensorial 225). The emergency was declared on 18 September (DS 097-2024-PCM,
23 districts of Amazonas, San Martín and Ucayali); Cajamarca had asked on 2 September and was declared on 25 September
(DS 099-2024-PCM).

With a consistent record the question has an answer:

- September 2024 was the **highest September since 2003** (rank 1 of 23), **+42 %** above the median of
  2012–2023 (same instrument) and +48 % above the 2003–2023 median.
- On 18 September, national activity over the previous 14 days was **1.6× the median** for those dates.
  It had been above every year since 2003 since **September 13**, and above the 90th percentile since
  September 11.
- Amazonas was at **3.1× its median**, above its record since September 8. Ucayali was at
  1.7×. San Martín, also in the decree, was **not** unusual (1.2×).
- Seven departments set a September record: Ucayali, Loreto, Cajamarca, Amazonas, La Libertad, Ancash, Ica.

This is a retrospective reading: the thresholds were chosen after the fact, so it shows what the evidence said, not a
tested alert.

### 1.3 Who needs a consistent record, and for what decision

| User | Decision | What they use today | What NINA adds |
|---|---|---|---|
| CENEPRED | Forest-fire risk scenarios; they set the 488 very-high-risk and 276 high-risk priority districts of the Plan Multisectorial 2025–2027 | Hotspots 2003–2022 from MODIS and VIIRS pooled, with no stated harmonization | A multi-year input that does not jump in 2012 or in 2026 |
| SERFOR monitoring, regional governments (COER) | When to escalate, where to concentrate prevention, whether to request an emergency | Last-24-hour hotspot alerts, no historical baseline | "Is this normal for here and now?" for any department or drawn area, with month-to-date comparison |
| Defensoría, journalists, researchers | Is fire increasing? Where is it under-reported? | INDECI reports (driven by reporting effort) or raw satellite counts (broken by sensor changes) | Detected vs reported, with one comparable series |

Hotspot counts are not a formal trigger for an emergency declaration in Peru (DS 074-2014-PCM uses qualitative
criteria: regional capacity exceeded). NINA provides evidence for that discussion; it does not replace it.

## 2. What NINA does, and what it does not

| Does | Does not |
|---|---|
| Harmonized burning-activity calendar from July 2002 to today, sensor-independent | Predict fires. We tested it: July–August activity anticipates an above-normal September **61 %** of the time nationally and **61 %** by department, against 50 % by chance: a weak signal, not a forecast. We do not claim forecasting. |
| Any area: country, Peruvian department, drawn polygon | Real-time alerts (SERFOR and FIRMS already do that) |
| Current month against history, including the month in progress | Count fires, burned area, causes or spread |
| Detected vs reported (INDECI) | Support tactical or local-scale decisions (FIRMS disclaimer) |
| CSV/ZIP with FIRMS citation, version, filters and date | Present unvalidated domains: they are shown as missing, never as zero |
| Continuity across the end of S-NPP through a validated NOAA-20 bridge | |

## 3. Why the numbers can be trusted (Validity)

- **Unit:** active H3 cells per day, not pixels, so resolution differences shrink before calibration.
- **Calibration:** VIIRS S-NPP / MODIS ratio per country × biome × calendar month × sampling regime, trained only on
  standard-quality data in the 2012–2025 overlap. NOAA-20 is bridged to S-NPP the same way.
- **Validation:** leave-one-year-out over 2012–2025 in five countries on four continents (Peru, Brazil, Australia,
  Indonesia, USA). For Peru with Terra+Aqua, the out-of-sample total bias is +0.4 %; year by year the error is
  typically ±10 % (median 6 %, 90th percentile 21 % in passing strata).
- **Independent check:** INPE's series (MODIS Aqua only) and NINA's (VIIRS S-NPP after 2012) are different instruments.
  They agree year to year with **r = 0.95** in 2012–2025, share the same four most active years (2005, 2020, 2010, 2024; INPE swaps the last two) and the same top
  Septembers (2024, 2012, 2022), and their ratio does not jump in 2012 (3.65 → 3.92).
- **Honest gaps:** a day without valid data is missing, not zero; months with missing days have no comparable value;
  strata that fail validation abstain; Terra-only years (2000–2002) are not served.

## 4. How this maps to the jury rubric

| Criterion | Question | NINA's answer | What to show |
|---|---|---|---|
| **Creativity** | New, or an improvement? | An improvement with a new piece: nobody publishes a validated MODIS→VIIRS bridge for hotspot counts, nor detected-vs-reported for Peru | The 2012 jump disappearing (raw vs harmonized) |
| **Diversity** | Do profiles complement each other? | See team table below | Who did what, in one slide |
| **Relevance** | Does it answer the challenge? Useful, easy? | It is the challenge: harmonized calendar, area of interest, date range, anomalies vs history, current month vs median, detected and reported, CSV | Live: pick a department → calendar → current month → download |
| **Impact** | Big problem? Many people? | Fire seasons affect 22 of 25 departments (2024); the tool serves national planners, regions, press and researchers, and the method is global | September 2024 replay and the INDECI gap |
| **Validity** | Scientifically valid? Real world? | Out-of-sample validation in five countries, independent agreement with INPE, published error, abstention | One slide with r = 0.95 and the per-year error |
| **Presentation** | Story: challenge, solution, why it matters | Three beats below | 3-minute demo |

**Team (fill in):**

| Member | Background | Role in NINA |
|---|---|---|
| | | Data and harmonization (pipeline, validation) |
| | | UX/UI and frontend |
| | | Backend (API, accounts, exports) |
| | | |

## 5. Status and limits

- The harmonized product is **experimental**. The NOAA-20 bridge passes its publication gate; the MODIS gate fails by
  count of strata (66 % pass against 80 % required), although passing strata hold 99.1 % of the activity. The
  static-source mask recovers about 44 % of reference static cells (gate: 80 %). Thresholds were not lowered; details in
  `docs/BACKEND_STATUS.md`.
- The long history covers five countries; elsewhere only 2025–2026 is available.
- The ratio between sensors depends on activity level; close rankings of MODIS-era years should not be over-read.
- See `docs/adr/0005-audit-fixes-0.4.0.md` for the audit and its fixes.

## 6. The pitch in three beats

1. **The record broke twice.** 2012 (MODIS → VIIRS, ×4.5 jump) and 2 November 2026 (S-NPP ends; MODIS
   follows). And the official count of reported fires grew ×10 for reasons that are not fire.
2. **We repaired it, and proved it.** One unit, a validated bridge, abstention where we cannot validate, and an
   independent instrument that agrees with r = 0.95.
3. **So what.** September 2024: the record said "unusual" days before the decree; it also says where fires burn without
   being reported. Pick any area and month, and download the evidence with its citation.

## Sources

- NASA FIRMS, MODIS C6.1 and VIIRS 375 m C2 active fire products (citations in `docs/DATA_SOURCES.md`).
- INDECI/SINPAD emergencies 2003–2025, datosabiertos.gob.pe (ODC-BY).
- INPE Programa Queimadas, Peru statistics, data.inpe.br/queimadas.
- DS 097-2024-PCM and DS 099-2024-PCM, El Peruano.
- Defensoría del Pueblo, Informe Defensorial 225 (2024).
- CENEPRED, Escenario de riesgo por incendios forestales (July 2024); Plan Multisectorial ante Incendios Forestales
  2025–2027 (DS 010-2025-PCM).
- Schroeder et al. (2014), *Remote Sensing of Environment* 143, 85–96, doi:10.1016/j.rse.2013.12.008.
- Giglio, Schroeder & Justice (2016), *Remote Sensing of Environment* 178, 31–41, doi:10.1016/j.rse.2016.02.054.
- Giglio et al. (2010), *Biogeosciences* 7, 1171–1186, doi:10.5194/bg-7-1171-2010 (cross-calibrating fire sensors in an
  overlap period to extend a record).
