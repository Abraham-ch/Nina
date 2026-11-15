# NINA · Data sources and readiness

**Current status 0.2:** [STATUS_V2.md](STATUS_V2.md). The archive gathers 2,108,030 unique observations in 57 loaded files: 48 Peruvian national files, 3 global NRT files from 14 Nov 2026 and 6 MODIS SP windows for the Australian rectangle in September 2025. FIRMS availability was actually verified with a MAP_KEY and the monthly acquisition was run from the interface. The filtered catalog, without credentials, is in `data/catalog/firms-availability.json`. Reference cartography uses NASA GIBS and Natural Earth 110m. Earthdata credentials are configured locally; scientific L2 download/reading is still pending. The 0.1 reviews below keep the earlier context.

**Update after implementing 0.1:** the public index `/data/country/yearly_summary_files.txt` used by the FIRMS page was verified, its 48 national files were downloaded and 2,034,899 detections were imported. The CSVs take exactly 163,067,831 bytes. [Application usage](../README.md), [updated status](STATUS_V1.md) and `data/inventory.json` document this run. The documentary review sections below keep the earlier state where there was no new check; the current implementation state is in `STATUS_V1.md`.

**Current scope: global, with per-area/period acquisition and explicit availability.** The execution order is in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). The full global history and global scientific validation are not declared complete.

> Current location: `DATA_SOURCES.md`, at the workspace root. The observation pipeline is implemented in `nina/` and `scripts/`. `docs/DATA_SOURCES.md` and `data/sources.yaml` are not paths used by version 0.1.
> Initial documentary review: 13 Nov 2026. Later the national public archive was downloaded and imported and samples of CMR metadata were queried. Credentials and authenticated L2 downloads remain pending.
> ⚠️ marks a path or condition pending verification. A documented URL is not the same as a downloaded, read and validated file. The ING/HAR/GAP/AUX identifiers of the draft are planning references; they do not certify implemented tasks.

## Review result

**Version 0.1 already has a prepared national set of observed detections; scientific harmonization with valid opportunities remains pending.** The hackathon resource provided by the team links to [NASA FIRMS](https://www.earthdata.nasa.gov/data/tools/firms); it is a portal of products and services, not a training package or an already harmonized series.

The Resources text received confirms that central source. It does not establish that all the auxiliaries in this document are mandatory. Automatic access to the challenge page failed during the review, so it is not certified that the shared excerpt covers all its tabs or future additions.

Main corrections: NOAA-21 has a standard source in `area` and `data_availability`; the NOAA-21 FIRMS archive starts on 1 Mar 2023; the `area` and `country` APIs document different limits; L2 products for observation opportunities are added and what remains to be validated is clarified. See sections 4–6.

## 0. Required credentials

| Environment variable | What for | How to obtain it |
|---|---|---|
| `FIRMS_MAP_KEY` | FIRMS API (32 hexadecimal characters) | https://firms.modaps.eosdis.nasa.gov/api/map_key/ |
| Earthdata Login through the mechanism the service supports (e.g. `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` or `~/.netrc`) | Protected downloads and scientific L2/auxiliary products. Confirm authentication per service; a MAP_KEY does not replace Earthdata Login | https://urs.earthdata.nasa.gov/ |
| — | University of Maryland SFTP (public credentials, published in the MODIS guide §4.3) | server `fuoco.geog.umd.edu`, user `fire`, password `burnt` |

Credentials are never committed. They are read from environment variables or from `~/.netrc`.

---

## 1. Hotspots · NASA FIRMS

### 1.1 Sensor status (as of 13 Nov 2026)

| Sensor | API source (NRT / standard) | Coverage | Status |
|---|---|---|---|
| MODIS C6.1 (Terra + Aqua) | `MODIS_NRT` / `MODIS_SP` | 1 Nov 2000 → today | Active. NASA recommends migrating to other sources; Terra is the only morning overpass |
| VIIRS S-NPP | `VIIRS_SNPP_NRT` / `VIIRS_SNPP_SP` | 20 Jan 2012 → **2 Nov 2026** | ⛔ **No new data since 2 Nov 2026**. The history remains available |
| VIIRS NOAA-20 | `VIIRS_NOAA20_NRT` / `VIIRS_NOAA20_SP` | 1 Apr 2018 → today | Active. **The standard source (`_SP`) already exists in the API** |
| VIIRS NOAA-21 | `VIIRS_NOAA21_NRT` / `VIIRS_NOAA21_SP` | **1 Mar 2023 → present, in the FIRMS archive** | Both sources documented in `area` and `data_availability`. Check effective dates before downloading; the `country` page does not list `_SP` yet |
| Landsat | `LANDSAT_NRT` | 20 Jun 2022 → today | Excluded from the project (US/Canada only) |

Sources: [FIRMS archive](https://firms.modaps.eosdis.nasa.gov/download/), [Area API](https://firms.modaps.eosdis.nasa.gov/api/area/), [availability](https://firms.modaps.eosdis.nasa.gov/api/data_availability/) and [S-NPP transition](https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know). The dates in this table correspond to the FIRMS point archive, not necessarily to the start of each L2 product or every NRT/SP variant.

**Decision for NINA:** keep S-NPP for the history and the overlap experiments; use NOAA-20 and NOAA-21 for recent continuity, evaluating each platform. The end-of-delivery notice does not remove the S-NPP history. "Present" in a catalog does not certify availability of the last day.

### 1.2 REST API (requires `FIRMS_MAP_KEY`)

Base: `https://firms.modaps.eosdis.nasa.gov`

| Service | URL | Use in the project |
|---|---|---|
| Hotspots by area (most recent) | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}` | Daily NRT job |
| Hotspots by area from a date | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}/{YYYY-MM-DD}` | Incremental fills and NRT → standard reprocessing |
| Hotspots by country | `/api/country/csv/{MAP_KEY}/{SOURCE}/{ISO3}/{DAY_RANGE}[/{YYYY-MM-DD}]` | Alternative to `area` for a country (e.g. `PER`) |
| Date availability | `/api/data_availability/csv/{MAP_KEY}/{SOURCE\|ALL}` | Pattern confirmed in the [documentation](https://firms.modaps.eosdis.nasa.gov/api/data_availability/); authenticated query pending. Service dates, not valid coverage of each AOI |
| Dates without data | [Published missing data table](https://firms.modaps.eosdis.nasa.gov/usfs/api/missing_data/) | Documents missing days per satellite/type. Data endpoint and scope applicable to Peru pending; do not assume that `/api/missing_data/` exists or that it diagnoses local cloudiness |
| MAP_KEY status | `/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}` ⚠️ | Check transaction usage |
| API documentation | https://firms.modaps.eosdis.nasa.gov/api/area/ · https://firms.modaps.eosdis.nasa.gov/api/country/ · https://firms.modaps.eosdis.nasa.gov/api/data_availability/ | Separate documentation from routes that return CSV |

- `AREA` = `west,south,east,north` in decimal degrees (e.g. Peru ≈ `-81.4,-18.4,-68.6,-0.03`), or `world`.
- **Limits**: 5000 transactions every 10 minutes per MAP_KEY. Large requests can consume multiple transactions; do not assume a fixed equivalence between request and transaction.
  The [`area` API](https://firms.modaps.eosdis.nasa.gov/api/area/) documents `DAY_RANGE` **1–5**; the [`country` API](https://firms.modaps.eosdis.nasa.gov/api/country/) documents **1–10**. Configure and check per endpoint. For the first `area` client, use a maximum of 5; do not send 10 because another API allows it.
- **RT** and **URT** (near real time) data are removed when the corresponding NRT data are processed, or after 6 h.

### 1.3 Direct-access NRT files (recent windows; download pending a test)

Candidate backup routes. The HTTP response, content and access requirement of each file were not checked in this review. Validate redirects, CSV header and last acquisition; a login page returned as HTML is not a correct data download.

Pattern: `https://firms.modaps.eosdis.nasa.gov/data/active_fire/{folder}/{format}/{PREFIX}_{Region}_{24h|48h|7d}.{ext}`

| Sensor | Folder | Prefix | Example (global, 7 days, CSV) |
|---|---|---|---|
| MODIS C6.1 | `modis-c6.1` | `MODIS_C6_1` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_7d.csv |
| NOAA-20 | `noaa-20-viirs-c2` | `J1_VIIRS_C2` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv |
| NOAA-21 | `noaa-21-viirs-c2` ⚠️ | `J2_VIIRS_C2` ⚠️ | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_7d.csv ⚠️ |
| S-NPP (frozen) | `suomi-npp-viirs-c2` | `SUOMI_VIIRS_C2` | no longer updated |

- Candidate regions: `Global`, `South_America` ⚠️, `Central_America` ⚠️, etc. The draft mentioned `J1_VIIRS_C2_Northern_and_Central_Africa_24h.csv`; that file was not downloaded again in this review.
- Shapefile: `.../{folder}/shapes/zips/{PREFIX}_{Region}_{period}.zip` (e.g. `.../modis-c6.1/shapes/zips/MODIS_C6_1_Europe_24h.zip`).
- Use: **backup** for the NRT job when the API fails. Not useful for the history.

### 1.4 Daily text files (last ~2 months, with Earthdata Login)

- Main: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS
- Backup: https://nrt4.modaps.eosdis.nasa.gov/archive/FIRMS
- Guide: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS/README.pdf
- Proposed use: diagnosing recent ingestion. Check retention and access; global counts do not certify coverage of an AOI.

### 1.5 Bulk history

| Resource | URL | Notes |
|---|---|---|
| Archive download tool | https://firms.modaps.eosdis.nasa.gov/download/ | The page documents CSV, SHP and JSON, authentication through Earthdata or an email code, and delivery of instructions by email. The initial importer will use CSV; completing a request and validating its real file is pending |
| Annual summaries by country (CSV) | https://firms.modaps.eosdis.nasa.gov/country/ | One file per country and year. The fastest way to load a country's history (e.g. Peru) |
| Public index of annual files | https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt | Verified and used by `scripts/bootstrap_data.py`: provides name, bytes and update date. The 48 `*_Peru.csv` files published when the index was queried were downloaded |
| Global monthly MCD14ML (MODIS) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD14ML/MCD14ML.YYYYMM.006.03.txt.gz` (or `C61` ⚠️) | Detection files to aggregate by date/platform. Path, collection and parser pending a check against a real file and its guide; a zero count alone does not prove an observation failure |
| Monthly VIIRS (UMD) | `sftp://fuoco.geog.umd.edu` → `data/VIIRS/C1/VNP14IMGML` ⚠️ | Optional: VIIRS equivalent of MCD14ML (check the available collection) |

### 1.6 Product documentation and DOIs for citation

| Product | Page / document | Dataset DOI |
|---|---|---|
| MCD14DL (MODIS NRT) | https://www.earthdata.nasa.gov/node/13777 | 10.5067/FIRMS/MODIS/MCD14DL.NRT.0061 |
| MCD14ML (MODIS standard) | MODIS C6/C6.1 guide v1.0: https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf | 10.5067/FIRMS/MODIS/MCD14ML |
| VNP14IMGTDL_NRT (S-NPP) | https://www.earthdata.nasa.gov/node/13827 | 10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002 |
| VJ114IMGTDL_NRT (NOAA-20) | https://www.earthdata.nasa.gov/node/13826 | 10.5067/FIRMS/VIIRS/VJ114IMGT_NRT.002 |
| VJ214IMGTDL_NRT (NOAA-21) | https://www.earthdata.nasa.gov/node/13825 | see the product page |
| MODIS/VIIRS attributes | https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs | — |
| VIIRS 375 m algorithm guide | https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf | — |
| End of S-NPP in FIRMS | https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know | — |
| History of alerts and outages | https://www.earthdata.nasa.gov/data/alerts-outages/content/data-alert-history/21880 | — |

---

## 2. Auxiliary data

| Data | URL | Notes |
|---|---|---|
| **GADM 4.1 administrative boundaries** | Pattern: `https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{ISO3}.gpkg` (e.g. `gadm41_PER.gpkg`). SHP index: https://geodata.ucdavis.edu/gadm/gadm4.1/shp/ | The [published license](https://gadm.org/license.html) allows academic/non-commercial use and requires prior permission for **redistribution or commercial use**. Do not include the file in a public download or repository by default; choose a geometry with terms suited to NINA's use |
| Official boundaries of Peru (INEI/IGN) | INEI open data portal ⚠️ | Optional, to get official names |
| **RESOLVE 2017 ecoregions** | Shapefile (~150 MB, CC-BY 4.0): https://storage.googleapis.com/teow2016/Ecoregions2017.zip ⚠️ · Viewer: https://ecoregions2017.appspot.com/ · Earth Engine: `RESOLVE/ECOREGIONS/2017` | 846 ecoregions, 14 biomes. Strata for HAR-01 |
| **MCD12Q1 v6.1** (land cover, 500 m, annual) | DOI: https://doi.org/10.5067/MODIS/MCD12Q1.061 · [Product catalog](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061) · Regional subsets: https://appeears.earthdatacloud.nasa.gov/ | Urban class = IGBP 13 (`LC_Type1`). Includes `LW`. The catalog confirms **caution for 2021 onwards** because the training data are out of date. Optional context/stratification; it does not replace an observation mask for each overpass |
| GHSL (urban areas, alternative) | https://human-settlement.emergency.copernicus.eu/ ⚠️ | Alternative to MCD12Q1 for the urban mask after 2021 |
| **Volcanoes · Smithsonian GVP** (Volcanoes of the World v5.4.0, 7 Aug 2026) | Database: https://volcano.si.edu/ · DOI: https://doi.org/10.5479/si.GVP.VOTW5-2026.5.4 · WFS (GeoJSON): `https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=json` ⚠️ | Cite the version and download date |
| **MCD64A1 v6.1** (burned area, optional) | DOI: https://doi.org/10.5067/MODIS/MCD64A1.061 · `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD64A1` | Complementary cross-check, not a truth equivalent to hotspots nor evidence fully independent of MODIS; document the algorithm's dependencies |
| **MOD14CMQ / MYD14CMQ** (0.25° grid, monthly, optional) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/Mx14CMQ` ⚠️ | Aggregated diagnostic that requires checking content and version. Its monthly/0.25° scale does not replace the per-cell/per-overpass observation opportunities of the proposed method |
| IANA time zones | Releases: https://github.com/evansiroky/timezone-boundary-builder/releases → `timezones-with-oceans.geojson.zip` | Local date in the API (ODbL license, OSM data) |
| LP DAAC / LAADS repositories | https://lpdaac.usgs.gov/ · https://ladsweb.modaps.eosdis.nasa.gov/ | MODIS land and level-1 products |

These auxiliaries are design choices, not a list of hackathon requirements. For the Peruvian pilot `America/Lima` can be declared without adding a global time-zone layer yet. Do not automatically exclude urban, agricultural or industrial hotspots: the challenge statement includes anthropogenic burning; any filter must be explicit and configurable.

---

## 3. Recommended download strategy

| Need | Source | Frequency |
|---|---|---|
| MODIS history of the region (2000-11 → latest standard) | CSV archive or country summaries | Initial load + periodic revision check |
| VIIRS S-NPP history (2012-01-20 → 2026-11-02) | Archive download tool (`VIIRS_SNPP_SP`) | Historical load and revision control: new acquisition has ended, but versions or reprocessing may change |
| VIIRS NOAA-20 history (2018-04 →) | Archive download tool or `VIIRS_NOAA20_SP` API | Once + incremental |
| VIIRS NOAA-21 history (FIRMS archive from 2023-03-01) | Archive or `area` with `VIIRS_NOAA21_SP`, after checking availability | Historical load + incremental; do not assume identical support in `country` |
| Recent (NRT) | `area` API with `MODIS_NRT`, `VIIRS_NOAA20_NRT` and `VIIRS_NOAA21_NRT` | Daily |
| Replacing NRT with standard | Archive/API, `_SP` and `data_availability`; check range and volume | Periodic review. Keep versions to reproduce results; the FIRMS archive indicates a lag of about 5 months, not a guaranteed delay |
| Availability diagnosis | Catalog/missing-data table + ingestion and granule checks | Global counts serve as a diagnostic signal; alone they do not identify local coverage or prove that a day without hotspots is a gap |

---

## 4. Data missing from the catalog for the proposed harmonization

FIRMS points are enough to start importing detections, display maps and build raw counts per sensor. NINA's architecture adds a scientific goal: estimating counts under a common observation protocol. For that method, valid opportunities must be rebuilt, including observed zeros. The following products are not new requirements attributed to NASA; they are inputs needed for that methodology.

| Platform | L2 fire product | Format | Start stated by the L2 catalog | Use |
|---|---|---|---|---|
| Terra MODIS | [MOD14 C6.1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod14-061) | HDF4 | 24 Feb 2000 | Mask, quality and bridge for the history before Aqua |
| Aqua MODIS | [MYD14 C6.1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-myd14-061) | HDF4 | 4 Jul 2002 | Initial instrument reference proposed for NINA |
| S-NPP VIIRS | [VNP14IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp14img-002) | NetCDF-4 | 17 Jan 2012 | Training and evaluation in the overlap; history after the end of new delivery |
| NOAA-20 VIIRS | [VJ114IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vj114img-002) | NetCDF-4 | 1 Jan 2018 | Continuity and cross-platform transfer test |
| NOAA-21 VIIRS | [VJ214IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vj214img-002) | NetCDF-4 | 10 Feb 2023 | Recent continuity and an additional per-platform test |

**L2 dates differ from those of the FIRMS point archive.** The catalog state or the `_SP` suffix do not guarantee that any day/AOI is complete: check availability and verify the effective granules.

### Geolocation, masks and quality

- Explicitly add the geolocation matching the product and collection. The VIIRS catalogs consulted point to `VNP03MODLL`, `VJ103MODLL` and `VJ203MODLL`, respectively. The guide and a real granule must confirm how to align those data with the mask; do not assume matching dimensions across all layers.
- For MODIS, check in the guide the included geolocation and the dependencies needed for the full mask and the geometry, using the corresponding geolocation products where appropriate. No untested binary path is fixed yet.
- Read mask, quality, fill, water, cloud and no-observation codes according to the version. A point `confidence` column does not replace those states.
- Record overpass time, observation geometry and exposure. If a required variable is not in the chosen product, add its documented dependency or limit the method.
- Distinguish MODIS Terra from Aqua even when obtained from a combined FIRMS source. Comparing all morning and afternoon overpasses as if they were equivalent would introduce a bias.
- Do not add VIIRS platforms together in a way that adding another satellite duplicates the target sampling. Keep platform, opportunity and reference protocol.

Before scaling, download and read at least one pair of products per target platform/collection, with its geolocation, to check the HDF4/NetCDF driver, fields, units, dimensions, masks and alignment. In 0.1, documentation and samples of CMR granule metadata were verified through `scripts/inventory_l2.py`; the L2 scientific content has not been read yet.

### Auxiliaries and cross-checks

For the first version, a well-defined AOI and the data required by the observation protocol are enough. Ecoregions, land cover, persistent thermal sources and burned area are added when they answer a question or improve an evaluation.

The [RESOLVE page](https://developers.google.com/earth-engine/datasets/catalog/RESOLVE_ECOREGIONS_2017) confirms 846 ecoregions and CC-BY 4.0; that alone does not verify the draft's ZIP link. The MCD12Q1 warning from 2021 is confirmed in its [catalog](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061). The GVP, GHSL, SFTP and direct-file routes keep their pending-test state where appropriate; no exhaustive download validation of each auxiliary was done.

## 5. What we have and what is missing

| Item | State checked in the workspace | Criterion to consider it ready |
|---|---|---|
| Published challenge resource | Text provided by the team: link to FIRMS | Keep provenance; review any extension by the organizer |
| Architecture and experience | `ARCHITECTURE.md` and `nina-demo.html` exist | Keep the distinction between prototype and real results |
| Source inventory | Cross-checked documentation; candidate routes marked | Fix products, collections, availability and ingestion contract |
| Credentials | Not configured when 0.1 was delivered; public download verified | Correct authenticated query and scientific download |
| National dataset | 48 CSVs, 2,034,899 unique detections, hashes and Parquet | Add L2 inputs and recent data by another route |
| National geometry | Versioned geoBoundaries, 2008 representation; 5,452 detections without a department in that geometry | Evaluate the current official geometry and keep traceability |
| Pipeline | Resumable download, ingestion, technical deduplication and Parquet export implemented | Complete L2 opportunity processing |
| Harmonization | Two exploratory Poisson models fitted to counts, with a held-out benchmark | Validate the scientific method with exposure, masks and platform bridges |
| Real calendar | React application/API connected to the observed national archive | Add a validated harmonized series and coverage |
| Assistant | Local engine connected to real analyses; LLM adapter prepared | Test a configured external provider and evaluate with users |

The Resources publication resolves the uncertainty about the central source. It does not automatically turn a catalog of URLs into a ready dataset, nor does it prove that a model works. Nor does it provide, in the text received, training/test labels or an already prepared official benchmark.

## 6. How to proceed: national implementation

The [implementation plan](IMPLEMENTATION_PLAN.md) replaces the earlier sequence centered on a Madre de Dios pilot. It defines 18 tasks with dependencies, proposed owners and verifiable results.

The first acquisition is organized for all of Peru. Historical detections per source/period and the L2 granules and dependencies that intersect the country are inventoried. After testing formats and access with small batches, the resumable national download is run. The small batches are a technical test, not a reduction of the territorial scope.

The total volume in bytes is not known yet: it must be measured in the inventory, distinguishing cumulative download, permanent storage and temporary space. Overpass files can extend beyond the country; selecting Peru does not mean automatically receiving all the scientific products clipped.

The first functional milestone of querying and exporting real national observations is already implemented. The harmonized calendar requires valid opportunities and evaluation on held-out regions/periods with diverse conditions. The local assistant already queries the observed outputs; connecting an LLM provider and the full scientific phase keep their pending states.

## 7. National and regional references (problem statement and validation)

Used by `scripts/evidence/peru_case.py`. Stored under `source/downloads/national/` (not versioned). None of them feeds the
harmonization: they frame the problem and give an independent check.

| Source | What it is | Download | Use in NINA |
|---|---|---|---|
| INDECI / SINPAD emergencies, 2003–2025 | One row per registered emergency (date, ubigeo, department, hazard, deaths, injured…), `;`-separated, Latin-1, ODC-BY | <https://www.datosabiertos.gob.pe/sites/default/files/BD_2003-2025_EMERGENCIAS.csv> (2026 first semester: `BD_2026_Semestre_I.csv`, new schema) · dictionary: <https://www.datosabiertos.gob.pe/dataset/emergencias-y-da%C3%B1os-nivel-nacional-por-departamento> | "Reported" side of *detected and reported*: rows with `PELIGRO = INCENDIO FORESTAL`. Counts emergencies with damage assessment, not all burns; INDECI's own 2024 totals differ between releases (1,754 to 2,746). |
| INPE Programa Queimadas, Peru | Monthly hotspots by department from one reference satellite (NOAA-12 until 2002-07-03, MODIS Aqua afternoon pass since 2002-07-04) | <https://data.inpe.br/queimadas/estatisticas/media/estatistica/paises/peru.json> | Independent cross-sensor check of NINA's series in 2012–2025 (INPE = MODIS Aqua, NINA = VIIRS S-NPP). INPE has not published how it will join its series once Aqua stops. |
| DS 097-2024-PCM, El Peruano | First state of emergency for forest fires, 18 Sep 2024, 23 districts of Amazonas, San Martín and Ucayali | <https://busquedas.elperuano.pe/dispositivo/NL/2326734-1> | Date of the retrospective replay. DS 099-2024-PCM (Cajamarca, Huánuco, Lambayeque): <https://busquedas.elperuano.pe/dispositivo/NL/2329467-1> |
| CENEPRED national risk scenario for forest fires (July 2024) | Uses hotspots 2003–2022 from VIIRS S-NPP and MODIS Terra/Aqua as an input, with no stated harmonization; it sets the priority districts of the Plan Multisectorial 2025–2027 | <https://sigrid.cenepred.gob.pe/sigridv3/documento/17792/descargar> | Shows an official user of multi-year hotspot counts that mixes sensors. |
| Defensoría del Pueblo, Informe Defensorial 225 (Sep 2024) | Conclusion 9.1: absence of centralized official information on forest fires | <https://www.defensoria.gob.pe/wp-content/uploads/2024/09/Informe-Defensorial-n.%C2%B0-225-Incendios-forestales.pdf> | Problem statement. |
