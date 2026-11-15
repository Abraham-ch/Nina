# ADR 0006 · Biome strata, noise ceiling and 31 calibration countries: method 0.5.0

Date: 2026-11-15 · Status: accepted (pre-registered before the 31-country run) · Amends ADR 0002 and ADR 0005

## Context

Candidate `e9f9a7a7a47bd640f9d27999` (method 0.4.0, five countries) fails the MODIS gates: 27 of 41 country × biome
strata pass for Terra + Aqua (65.9 %, threshold 80 %). The failure is not in the aggregate: leave-one-year-out over
2012–2025 gives relative bias +0.4 %, Spearman 0.975 and R² 0.989 over 6,762 monthly totals, and every year stays
within ±8 %. A stratum-by-stratum review of the 14 failing strata found three separate causes.

1. **A sentinel collision (bug).** `fit_coefficients` stores the country-wide fallback under `biome = 0`, and cells
   without a RESOLVE ecoregion also carry `biome = 0`. Those cells (58 % flagged as water: coastal and lake-shore
   cells) therefore never get their own coefficient; they receive the country-wide ratio (≈ 3.5 VIIRS per MODIS)
   although their real ratio is 15–30, because the MODIS land/water mask skips mixed coastal pixels that the 375 m
   VIIRS grid resolves. Result: −70 % to −93 % bias in all five `biome 0` strata, which hold under 0.5 % of activity.
2. **Strata below the noise ceiling.** In 9 of the failing strata (US tropical forests, tundra and mangroves;
   Indonesian conifer and montane forest; Peruvian mangroves) fires are few. There, even NOAA-20 — the same VIIRS
   instrument as the S-NPP reference, 50 minutes apart — reaches only Spearman 0.65–0.79 against S-NPP in 6 of them.
   A requirement that MODIS order the months better than the reference instrument reproduces itself cannot be met by
   any calibration. The calibrated Spearman equals the raw Spearman in these strata (the multiplicative calibration
   does not reorder months; it cannot recover fires MODIS never detected).
3. **Geographic transfer.** Applied to 166 countries outside the calibration set in 2026, the five-country MODIS
   calibration leaves a bias of −34 % (raw −71 %). Five countries do not cover the world's fire regimes: boreal
   Eurasia and Canada, African savannas, cropland burning in Asia and the Eurasian steppe are absent or marginal.

## Decision

Method version **0.5.0**. Bias and Spearman thresholds of the gates are unchanged (|bias| ≤ 10 % MODIS, ≤ 5 %
NOAA-20; Spearman ≥ 0.8; ≥ 80 % of evaluable strata).

| # | Change | Where |
|---|---|---|
| 1 | The aggregate fallback uses its own sentinel (`ALL_BIOMES = -1`). `biome 0` is an ordinary stratum ("no ecoregion", mostly coastal) with its own coefficient | `calibration.fit_coefficients`, `select_coefficient` |
| 2 | Fallback order: country × biome → **world × biome** → country (all biomes) → world (all biomes). The calibration unit of AGENTS.md §10.2 is the biome; a biome seen in other countries is a better prior than another biome of the same country | `calibration.select_coefficient` |
| 3 | **Noise ceiling** for the MODIS gates: a stratum is evaluable for Terra-only and Terra + Aqua only if NOAA-20 vs S-NPP reaches Spearman ≥ 0.8 in that stratum (leave-one-year-out). Strata below the ceiling are reported as `below_noise_ceiling`, never as passed, and the product abstains there exactly as for a failed stratum. The NOAA-20 gate itself is unchanged (the ceiling would be circular). Where NOAA-20 has no evaluable value for a stratum, the stratum stays evaluable (conservative) | `calibration.apply_noise_ceiling`, `io.model` |
| 4 | The strict fraction under the 0.4.0 rule (`strict_passed_fraction`) is reported next to the gate value, so the effect of rule 3 is always visible | `io.model`, validation report |
| 5 | **Leave-country-out transfer test** (reported, not gated): each calibration country is predicted with coefficients fitted without it, i.e. through the world × biome fallback. Reported per country: relative bias, Spearman, and the share of countries with |bias| ≤ 10 % and Spearman ≥ 0.8 | `calibration.validate_countries`, `io.model` |
| 6 | Calibration countries: from 5 to 31 (below). FIRMS file names in `io.acquire`; Natural Earth names in `config.CALIBRATION_COUNTRIES` | `io.acquire`, `config` |

### Why these 26 added countries

Selection rule, fixed before any 0.5.0 result was seen: (a) fire weight — share of the 2000–2025 FIRMS country
archive; (b) a fire regime or biome absent or marginal in the five-country set; (c) one or two countries per region
rather than many from one; (d) relevance to Peru (neighbours, shared Amazon and Chaco fire seasons); (e) a public
incident registry for independent validation where one exists; (f) the disk budget (≈ 19 GB of new raw files).

| Region | Countries | Reason |
|---|---|---|
| Africa | Dem. Rep. Congo, Zambia, Nigeria, Ethiopia, Madagascar, South Africa | DRC is the largest fire country of the archive (9.2 %); southern miombo (Zambia) and northern Sudanian savanna (Nigeria, also gas flares that test the static mask) burn in opposite seasons; Ethiopian highlands add montane grassland, a failing biome in 0.4.0; Madagascar island grasslands; South Africa fynbos (Mediterranean) and industrial static sources |
| Boreal and steppe | Russia, Canada, Kazakhstan, Mongolia | Boreal forest is marginal in 0.4.0 (Alaska only); Russia (6.2 % of the archive) and Canada (2.4 %, public CNFDB registry); Eurasian steppe and cropland stubble burning |
| Asia | India, China, Myanmar | Cropland residue burning (Punjab, North China Plain), industrial static sources, mainland South-East Asian slash-and-burn (March–April peak) |
| Americas | Mexico, Honduras, Bolivia, Colombia, Ecuador, Chile, Argentina, Paraguay, Venezuela | Peru's neighbours and the shared Amazon–Chaco fire season (Bolivia 2019 and 2024); Llanos savanna with a January–March season (Colombia, Venezuela); Pampas and Paraná delta (Argentina); Mediterranean Chile; Mesoamerican agricultural burning (Mexico, public CONAFOR registry; Honduras) |
| Mediterranean Europe | Portugal, Spain, Greece, Turkey | Mediterranean forest and scrub outside Australia and California, with public national fire registries (Portugal ICNF) and recent megafires (Greece 2023, Turkey 2021) |

Not chosen, with reason: Angola (2.9 GB), Mozambique (1.7 GB), South Sudan (1.5 GB), Central African Republic
(1.4 GB) — same regimes as DRC and Zambia at a high disk cost; Ukraine — war-related fires since 2022 would
confound vegetation fire statistics; most of Europe — little fire activity.

## Consequences

- New candidate identifier; the 0.4.0 candidate and its reports stay in git history and in `docs/`.
- Results of 0.5.0 are reported whatever they are, including gate failures, the strict fraction and the transfer
  test. Rule 3 was written from the 0.4.0 diagnosis; the 26 added countries are an out-of-sample check of it.
- The product keeps abstaining in strata that are not validated, so rule 3 never makes the app serve a harmonized
  value that the 0.4.0 rule would have served for a failing stratum without saying so.
