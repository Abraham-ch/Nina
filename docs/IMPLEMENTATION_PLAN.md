# NINA — Implementation plan and global evolution

**Current direction 0.2:** [current status](STATUS_V2.md). Implemented: atlas redesign with CesiumJS, 2D view, shared context, observer comparison, held-out experiment, mobile calendar, contextual evidence, shareable links and per-area/month acquisition. A global snapshot and an Australian month were verified, in addition to the Peruvian archive. Harmonization with valid opportunities, global scientific validation and managed deployment remain pending. The national sections below document the first phase and do not limit the current scope.

Updated on 13 November 2026. This is the main document to follow the work. The [architecture](ARCHITECTURE.md) explains the technical decisions and the [source catalog](DATA_SOURCES.md) documents the data. Development dates do not restrict the scope of this plan.

**Implementation update:** the local 0.1 application with real national history already exists. See [README.md](../README.md) to start it and [STATUS_V1.md](STATUS_V1.md) for the state of each task. The observation application and the exploratory models are available; harmonization with valid opportunities and user validation remain pending.

## 1. Recommended scope of the first delivery

**First phase already delivered: all of Peru.** Version 0.2 extends selection and acquisition to the world, keeping this set as a historical and validation case. The effective coverage state is published per window and scope.

The national recommendation allows evaluating a concrete product with users, contrasting coast, highlands and rainforest, and controlling the processing. It does not come from a demonstration that global scope is technically impossible. The 68 TB example mentioned in the conversation corresponds to one million geolocation files of 68.2 MB; it is not a calculation of the storage required by NINA or by the FIRMS point history.

The Peruvian scope includes:

- Detection history available since the early 2000s and recent updates.
- Calendar, comparison of the same month with its history, coverage and interpretation limits.
- Original observations and equivalent counts clearly identified.
- Sensor substitution lab with results measured outside training.
- Download of data, charts, methodology and provenance.
- Assistant that answers about the selected analysis and prepares reports with evidence.

The current HTML has three schematic areas and simulated data. It does not yet represent this connected national coverage. The first technical tests will use small periods to check reading and access; that does not change the geographic scope of the product. Madre de Dios can be one demo case among others, not the limit of the project.

## 2. How much information we need

### A. Full hotspot inventory for Peru

Goal: obtain every detection available for the territory in the selected sources, keeping platform, collection and revision. The FIRMS point archive publishes these start dates; effective standard and recent availability will be checked per source.

| Source | Target period | Purpose |
|---|---|---|
| MODIS Terra and Aqua, C6.1 | From 1 Nov 2000 to the latest available date | History; separate Terra/Aqua and validate the initial bridge |
| VIIRS S-NPP | 20 Jan 2012 to 2 Nov 2026, depending on archive availability | Historical overlap and continuity between instruments |
| VIIRS NOAA-20 | From 1 Apr 2018 to the latest available date | Overlap and recent observations |
| VIIRS NOAA-21 | From 1 Mar 2023 to the latest available date | Recent continuity and evaluation of another platform |

Source of periods and mechanisms: [FIRMS archive](https://firms.modaps.eosdis.nasa.gov/download/). The archive documents CSV, SHP and JSON and authentication through Earthdata or an email code. The initial importer will use CSV. The standard suffix alone does not guarantee that the last day is available.

The history will be downloaded in file/period batches, with resumption and integrity control. The API will serve bounded queries and updates. There is no need to load the whole country and every year into memory at the same time.

### B. Masks, geolocation and observation opportunities

For the proposed methodology we need MODIS/VIIRS L2 products and their dependencies, for the relevant periods and overpasses that intersect Peru. These files can contain a swath larger than the country: filtering the catalog by Peru does not guarantee a size reduction proportional to its area.

They will be selected by footprint and time, processed in batches and turned into compact observation-opportunity tables. The masks allow valid observations without detection to be distinguished from places without a valid observation. If a required scientific input is not available, the result must keep that state.

The initial download to check formats and the training sample are smaller than the final processing. **An output with scientific support in only a few examples will not be presented as a harmonized national calendar.** The national deployment will show explicitly where the method is validated and where the estimate cannot be issued.

### C. Complementary data

A national boundary and administrative divisions with adequate provenance and terms of use, plus auxiliaries justified by the evaluation. Land cover, ecoregions and burned area are candidates, not mandatory full downloads of the planet. For the Peruvian territory the civil zone `America/Lima` will be declared and UTC will also be kept.

### Volume: what is known and what is pending

**The national point archive is already measured:** 163,067,831 bytes of CSV, plus the database and Parquet documented in the delivery manifest. L2 granules and their dependencies have not yet been summed exhaustively; the total of the scientific project still lacks a complete sizing. The measured CSV volume is not confused with the storage of the whole solution.

Scale examples, purely illustrative:

- Ten million rows of 100 bytes per row would take about **1 GB** of CSV. This does not claim that Peru has ten million rows or that this is the size of its records.
- A thousand files of 68.2 MB would take about **68.2 GB**; a million, **68.2 TB**. NASA publishes 68.2 MB as the reference size for [VNP03MODLL](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp03modll-002). It has not been verified that each real file has that size.

They will be measured separately:

| Magnitude | How it is determined |
|---|---|
| Download bytes | Sum of inventory sizes, separating published data and unknown sizes |
| Permanent storage | Retained originals, normalized tables, opportunities, results and versions |
| Peak temporary space | Largest simultaneous batch, decompressed files and intermediate results |
| Processing memory | Measured on a representative real batch; not equal to the size of the full archive |
| Operating cost | Measured resources and rates of the chosen environment, after the inventory |

Retention policies are set with that inventory. The data used in the benchmark and its manifests will be kept for reproduction. When an auxiliary file is only kept in cache, its identifier/versioning, checksum and provenance will be recorded; reproducing it later will depend on keeping it or being able to retrieve it from the source.

## 3. Defined architecture

```text
FIRMS + L2 products intersecting Peru
                    ↓
Ingestion and quality controls — Python
                    ↓
Original objects + GeoParquet + PostgreSQL/PostGIS catalog
                    ↓
Valid opportunities → harmonization → held-out evaluation
                    ↓
Calendar and evidence — FastAPI + DuckDB
                    ↓
Web — React/TypeScript + MapLibre + SVG charts
                    ↓
Assistant with tools and reports with references
```

Scientific processing runs in a worker, separate from web requests. Queries use aggregates and partitions by platform, period and location. The first code organization will be a repository with data, science, API and web modules.

The reference deployment remains containers, object storage, PostgreSQL and a job queue; AWS is the route described in the architecture. Size and cost will be determined with measurements. Local development and deployment will use the same data contracts.

Extending to another country will require new data and evaluation of the method; parameterizing the country avoids coupling the software to Peru, but does not prove that a Peruvian model generalizes to the whole world.

## 4. Work order and deliverables

The following steps are ordered by dependency, without assigning arbitrary dates.

| Step | Result that must be ready | What it enables |
|---|---|---|
| 1. Preparation | National geometry, data contract, tested access and inventory with sizes | Know what will be downloaded and where to process it |
| 2. National detections | Raw history per source with controls, revisions and manifests | Query and export real observations for all of Peru |
| 3. Observation and science | Valid opportunities, pairs, baseline and evaluated model | Estimate a comparable series and know its limits |
| 4. Connected product | API, national map, calendar, comparison and export | Explore the country and particular areas with real data |
| 5. Useful assistant | Queries and reports by role with verified figures | Interpret the analysis and prepare communications |
| 6. Delivery close | Reproduction, user review and scientific demo | Defend results, usefulness and limitations |

The API and interface can advance with contracts and fixtures while the data are processed. Scientific figures and AI answers are connected only when identified and verifiable results exist.

## 5. Executable tasks

**State when this plan was created:** documented architecture, reviewed catalog and simulated demo available. The [updated task status after implementing 0.1](STATUS_V1.md) distinguishes what was done from what is pending; the following table keeps dependencies and completion criteria. E1 = data/science lead; E2 = product/platform lead. The split is proposed for the two engineers.

| ID | Task | Depends on | Owner | Completion criterion |
|---|---|---|---|---|
| N01 | Prepare repository, environment and modules | — | E2 | Reproducible environment; run commands documented |
| N02 | Fix geometries and the observation/analysis contract | — | Both | National AOI and divisions with provenance; UTC, units, states and versions defined |
| N03 | Test access and inventory sources by period and footprint | N02 | E1 | FIRMS query and L2 reading verified; inventory with known/unknown sizes and download mechanism |
| N04 | Measure a batch and size storage/processing | N03 | Both | Bytes, time, memory, temporary space and retention policy measured; local/cloud decision documented |
| N05 | Implement resumable download of the national history | N01, N03, N04 | E1 | Every requested partition has state, checksum and revision; failures and absences visible |
| N06 | Normalize and quality-control detections | N02, N05 | E1 | GeoParquet per source/period, technical deduplication, quality report and counts reconciled with originals |
| N07 | Build observation opportunities and pairings | N03, N04, N06 | E1 | Aligned masks; detections, valid zeros and unknowns separated; versioned temporal/spatial rules |
| N08 | Fix partitions and the national benchmark | N06, N07 | Both | Held-out regions and years; relevant coast/highlands/rainforest and cover types; leakage prevention |
| N09 | Fit baseline and candidate model | N08 | E1 | Out-of-sample comparison of error, bias, uncertainty and extremes; justified choice |
| N10 | Evaluate Terra–Aqua bridges and between VIIRS platforms | N08, N09 | E1 | Temporal/geographic scope and failures published; unsupported periods identified |
| N11 | Produce versioned calendar and evidence | N09, N10 | E1 | National and per-AOI aggregation; comparable median, partial month and correct support states |
| N12 | Implement query and jobs API | N01, N02 | E2 | Contracts, filters, states, per-revision cache and error handling; scientific connection requires N11 |
| N13 | Implement national map and selection | N02, N12 | E2 | All of Peru, divisions and polygons; scale-based loading and accessible navigation |
| N14 | Connect calendar, lab and exports | N11, N12, N13 | E2 | One selection shares figures and provenance across interface, CSV, charts and manifest |
| N15 | Integrate assistant tools and writing | N11, N12 | E2 | Queries by role, references to analyses and figure verification; template fallback |
| N16 | Evaluate the assistant and tasks with users | N14, N15 | Both | Insufficiency cases, AOI changes and false premises; comprehension and corrections documented |
| N17 | Add recent update and NRT→SP revision | N05, N06, N11 | E1 | Idempotent re-ingestion; revision without double counting; acquisition and update dates visible |
| N18 | Deploy, check reproduction and prepare the presentation | N14, N16, N17 | Both | Reproduced run, accessible product and demo with real results and one abstention case |

An early functional milestone ends with N06, N12 and N13: real national detections can be queried. The scientific version also requires N07–N11. The explanatory AI depends on that evidence; it does not determine the calendar values.

## 6. What we do immediately

The initial block of environment, public archive, download and local application was already done in 0.1. The next scientific dependency is **N07**: obtain and align masks/geolocation to build valid opportunities, together with L2 sizing and the remaining access checks of N03–N04. The current detail is in [STATUS_V1.md](STATUS_V1.md).

**Update 0.1:** the 48 public annual files for Peru were downloaded, 2,034,899 detections were imported and exploratory calibrations were fitted with a held-out test. No cloud infrastructure has been contracted and the model has not yet been validated with L2 masks and opportunities. "National coverage" means that the product supports the whole territory and communicates the real gaps; not that it fabricates observations where satellites provide no support.

## 7. Reference documents

- [DATA_SOURCES.md](DATA_SOURCES.md): sources, variants, dates, API limits and pending verification.
- [ARCHITECTURE.md](ARCHITECTURE.md): scientific method, components and the assistant contract.
- [nina-demo.html](../nina-demo.html): visual reference of the experience; simulated data.
- [Challenge statement](exa-results/nasa-space-apps-2026-2026-11-12/enunciado-a.txt): request for a calendar, region selection and downloads. The text provided allows areas of interest and does not require global coverage.
