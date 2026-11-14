# NINA 0.1 · Actual state of the delivery

Record of the original delivery. For the current state and the global extension see [STATUS_V2.md](STATUS_V2.md).

Local delivery date: 13 Nov 2026. [Usage instructions](../README.md).

## Available and verified

- React/TypeScript application with a FastAPI API and a local DuckDB database.
- 48 national NASA FIRMS files downloaded, with 163,067,831 bytes of CSV and SHA-256 hashes.
- 2,034,899 unique MODIS, S-NPP and NOAA-20 detections, between 2000 and 2025.
- Classification by the bundled geoBoundaries geometry; national detections without assignment to a division of the set are preserved.
- Real map with national selection, divisions and polygons, calendar, filters and descriptive comparison.
- CSV/JSON/TXT/SVG exports linked to the analysis and to the archive revision.
- Two exploratory Poisson calibrations, compared with a simple factor on held-out data.
- Deterministic assistant with evidence and an optional LLM adapter that keeps the numbers computed by the server.
- CSV import, persisted jobs and a recent-update client that can be enabled with a MAP_KEY.
- Install, resumable load and start scripts; container files prepared.
- Successful production build, 13 backend tests and 13 automated checks in Chrome, with visual review on desktop and mobile.

Backend tests use fixtures in separate directories. The synthetic scenarios were not imported into the real database.

## Material limits

1. **The final scientific harmonization is still pending.** L2 masks have not been downloaded/aligned and observation opportunities have not been built. The lab is an exploratory baseline, not a coverage-corrected series.
2. There is no NOAA-21 or 2026 data in the downloaded annual index. The interface shows them as unavailable and accepts new CSVs or recent queries with credentials.
3. NASA and language-provider credentials were not configured at delivery. The authenticated connection and the real LLM provider were not tested; the local assistant was.
4. The 2008 geometry of the set used contains 26 divisions; it is not a current official administrative certification. 5,452 detections are kept without an assigned department.
5. The calendar is grouped in UTC. Count comparisons are descriptive; no significance, fire prediction or causal attribution is claimed.
6. The local service uses a single process and DuckDB. PostgreSQL, S3 storage, a managed queue and AWS deployment remain as evolution architecture. Docker is prepared, without claiming a run that has not been checked.
7. Independent scientific review and validation with stakeholders remain pending; an automated test does not replace them.

## Relation to the plan

The following states avoid reading "functional version 0.1" as all scientific and deployment phases completed.

| Task | State in this delivery |
|---|---|
| N01 · Environment and modules | Implemented; pinned dependencies and documented commands |
| N02 · Geometry and contract | National implementation with versioned geometry; official boundary update pending |
| N03 · Access and inventory | Public index and CSV download verified; L2 metadata sampled, authenticated scientific access pending |
| N04 · Sizing | CSV, database and Parquet measured; full L2 budget pending |
| N05 · National download | Complete for the 48 files published in the index consulted; recent/NOAA-21 extension pending from another source |
| N06 · Normalization | Implemented and run; one technical duplicate detection and zero rejected rows in the initial archive |
| N07 · Valid opportunities | Pending aligned masks and geolocation |
| N08 · Benchmark | Implemented for exploratory monthly counts; opportunity benchmark pending |
| N09 · Models | Scale baseline and Poisson candidate computed; scientific validity of the harmonization pending |
| N10 · Sensor bridges | Not validated yet; unsupported periods are not filled in artificially |
| N11 · Scientific calendar | Observed calendar and exploratory calibration available; exposure-corrected series pending |
| N12 · API | Implemented and tested locally |
| N13 · National map | Implemented and checked in the browser |
| N14 · Exports | Implemented and checked with five real downloads |
| N15 · Assistant | Local engine tested; LLM adapter prepared, real connection pending configuration |
| N16 · Evaluation | Software tests completed; user evaluation pending |
| N17 · Update | Client and standard/provisional handling implemented and tested with fixtures; real authenticated call pending |
| N18 · Deployment and delivery | Local application built and run; cloud deployment and final scientific presentation pending |

## Next scientific phase

Configure access, obtain an L2 sample and its geolocation, verify masks/dimensions and build opportunities on a common support. Only then can the harmonization that controls for observation be trained and evaluated and its validated scope extended. The software in this delivery already allows querying, inspecting and exporting the data needed to study that next step.
