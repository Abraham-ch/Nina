# Fuentes de datos · URLs directas

> Ubicación en el repo: `docs/DATA_SOURCES.md`. La versión que el pipeline usa en ejecución es `data/sources.yaml` (ver AUX-01).
> Revisado: 13-nov-2026. Las URLs marcadas con ⚠️ siguen un patrón conocido, pero hay que confirmarlas con una petición real antes de fijarlas en el código.

## 0. Credenciales necesarias

| Variable de entorno | Para qué | Cómo se obtiene |
|---|---|---|
| `FIRMS_MAP_KEY` | API de FIRMS (32 caracteres hexadecimales) | https://firms.modaps.eosdis.nasa.gov/api/map_key/ |
| `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` (o `~/.netrc`) | Descarga de archivos de FIRMS, archivos de texto NRT diarios y productos de LP DAAC (MCD12Q1, MCD64A1) | https://urs.earthdata.nasa.gov/ |
| — | SFTP de la Universidad de Maryland (credenciales públicas, publicadas en la guía MODIS §4.3) | servidor `fuoco.geog.umd.edu`, usuario `fire`, contraseña `burnt` |

Nunca se commitean credenciales. Se leen de las variables de entorno o de `~/.netrc`.

---

## 1. Focos de calor · NASA FIRMS

### 1.1 Estado de los sensores (al 13-nov-2026)

| Sensor | Fuente en la API (NRT / estándar) | Cobertura | Estado |
|---|---|---|---|
| MODIS C6.1 (Terra + Aqua) | `MODIS_NRT` / `MODIS_SP` | 1-nov-2000 → hoy | Activo. NASA recomienda migrar a otras fuentes; Terra es el único paso de la mañana |
| VIIRS S-NPP | `VIIRS_SNPP_NRT` / `VIIRS_SNPP_SP` | 20-ene-2012 → **2-nov-2026** | ⛔ **Sin datos nuevos desde el 2-nov-2026**. El histórico sigue disponible |
| VIIRS NOAA-20 | `VIIRS_NOAA20_NRT` / `VIIRS_NOAA20_SP` | 1-abr-2018 → hoy | Activo. **Ya existe la fuente estándar (`_SP`) en la API** |
| VIIRS NOAA-21 | `VIIRS_NOAA21_NRT` | 17-ene-2024 → hoy | Activo (solo NRT) |
| Landsat | `LANDSAT_NRT` | 20-jun-2022 → hoy | Excluido del proyecto (solo EE. UU./Canadá) |

### 1.2 API REST (requiere `FIRMS_MAP_KEY`)

Base: `https://firms.modaps.eosdis.nasa.gov`

| Servicio | URL | Uso en el proyecto |
|---|---|---|
| Focos por área (lo más reciente) | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}` | Job NRT diario |
| Focos por área desde una fecha | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}/{YYYY-MM-DD}` | Rellenos incrementales y reprocesos de los NRT → estándar |
| Focos por país | `/api/country/csv/{MAP_KEY}/{SOURCE}/{ISO3}/{DAY_RANGE}[/{YYYY-MM-DD}]` | Alternativa a `area` para un país (p. ej., `PER`) |
| Disponibilidad de fechas | `/api/data_availability/csv/{MAP_KEY}/{SOURCE\|ALL}` ⚠️ | Saber hasta qué fecha llega el estándar de cada sensor (ING-09) |
| Fechas sin datos | `/api/missing_data/` ⚠️ (página: https://firms.modaps.eosdis.nasa.gov/usfs/api/missing_data/) | Huecos oficiales por satélite (GAP-06) |
| Estado de la MAP_KEY | `/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}` ⚠️ | Consultar el consumo de transacciones |
| Documentación de la API | https://firms.modaps.eosdis.nasa.gov/api/area/csv · https://firms.modaps.eosdis.nasa.gov/usfs/api | — |

- `AREA` = `oeste,sur,este,norte` en grados decimales (p. ej., Perú ≈ `-81.4,-18.4,-68.6,-0.03`), o `world`.
- **Límites**: 5000 transacciones cada 10 minutos por MAP_KEY. Una consulta de varios días cuenta como varias transacciones.
  El máximo de `DAY_RANGE` varía según la documentación (1–5 o 1–10): déjalo configurable (`FIRMS_MAX_DAY_RANGE`, por defecto `5`).
- Los datos **RT** y **URT** (casi en tiempo real) se eliminan cuando se procesan los NRT correspondientes, o pasadas 6 h.

### 1.3 Archivos NRT sin clave (últimos 7 días)

Patrón: `https://firms.modaps.eosdis.nasa.gov/data/active_fire/{carpeta}/{formato}/{PREFIJO}_{Región}_{24h|48h|7d}.{ext}`

| Sensor | Carpeta | Prefijo | Ejemplo (global, 7 días, CSV) |
|---|---|---|---|
| MODIS C6.1 | `modis-c6.1` | `MODIS_C6_1` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_7d.csv |
| NOAA-20 | `noaa-20-viirs-c2` | `J1_VIIRS_C2` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv |
| NOAA-21 | `noaa-21-viirs-c2` ⚠️ | `J2_VIIRS_C2` ⚠️ | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_7d.csv ⚠️ |
| S-NPP (congelado) | `suomi-npp-viirs-c2` | `SUOMI_VIIRS_C2` | ya no se actualiza |

- Regiones: `Global`, `South_America` ⚠️, `Central_America` ⚠️, etc. Ejemplo de región confirmada: `J1_VIIRS_C2_Northern_and_Central_Africa_24h.csv`.
- Shapefile: `.../{carpeta}/shapes/zips/{PREFIJO}_{Región}_{periodo}.zip` (p. ej., `.../modis-c6.1/shapes/zips/MODIS_C6_1_Europe_24h.zip`).
- Uso: **respaldo** del job NRT cuando la API falla. No sirven para el histórico.

### 1.4 Archivos de texto diarios (últimos ~2 meses, con Earthdata Login)

- Principal: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS
- Respaldo: https://nrt4.modaps.eosdis.nasa.gov/archive/FIRMS
- Guía: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS/README.pdf
- Uso: **conteos diarios globales** recientes para detectar huecos (ING-07).

### 1.5 Histórico masivo

| Recurso | URL | Notas |
|---|---|---|
| Herramienta de descarga del archivo | https://firms.modaps.eosdis.nasa.gov/download/ | Datos de más de 7 días en SHP, CSV o **JSON**. La solicitud se procesa de forma asíncrona y llega por email. Requiere Earthdata Login o código por email. Es la forma de obtener `DL_FIRE_*` |
| Resúmenes anuales por país (CSV) | https://firms.modaps.eosdis.nasa.gov/country/ | Archivo por país y año. La forma más rápida de cargar el histórico de un país (p. ej., Perú) |
| MCD14ML mensual global (MODIS) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD14ML/MCD14ML.YYYYMM.006.03.txt.gz` (o `C61` ⚠️) | **Conteos diarios globales MODIS 2000 → hoy** (ING-07). Texto de ancho fijo; formato en la guía §5.5 |
| VIIRS mensual (UMD) | `sftp://fuoco.geog.umd.edu` → `data/VIIRS/C1/VNP14IMGML` ⚠️ | Opcional: equivalente VIIRS de MCD14ML (revisar la colección disponible) |

### 1.6 Documentación de productos y DOI para citar

| Producto | Página / documento | DOI del dataset |
|---|---|---|
| MCD14DL (MODIS NRT) | https://www.earthdata.nasa.gov/node/13777 | 10.5067/FIRMS/MODIS/MCD14DL.NRT.0061 |
| MCD14ML (MODIS estándar) | Guía MODIS C6/C6.1 v1.0: https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf | 10.5067/FIRMS/MODIS/MCD14ML |
| VNP14IMGTDL_NRT (S-NPP) | https://www.earthdata.nasa.gov/node/13827 | 10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002 |
| VJ114IMGTDL_NRT (NOAA-20) | https://www.earthdata.nasa.gov/node/13826 | 10.5067/FIRMS/VIIRS/VJ114IMGT_NRT.002 |
| VJ214IMGTDL_NRT (NOAA-21) | https://www.earthdata.nasa.gov/node/13825 | ver la página del producto |
| Atributos MODIS/VIIRS | https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs | — |
| Guía del algoritmo VIIRS 375 m | https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf | — |
| Fin de S-NPP en FIRMS | https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know | — |
| Historial de alertas e interrupciones | https://www.earthdata.nasa.gov/data/alerts-outages/content/data-alert-history/21880 | — |

---

## 2. Datos auxiliares

| Dato | URL | Notas |
|---|---|---|
| **Límites administrativos GADM 4.1** | Patrón: `https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{ISO3}.gpkg` (p. ej., `gadm41_PER.gpkg`). Índice SHP: https://geodata.ucdavis.edu/gadm/gadm4.1/shp/ | **Licencia: gratis para uso académico y no comercial; el uso comercial requiere licencia.** Revisar antes de publicar la app |
| Límites oficiales del Perú (INEI/IGN) | Portal de datos abiertos del INEI ⚠️ | Opcional, para tener nombres oficiales |
| **Ecorregiones RESOLVE 2017** | Shapefile (~150 MB, CC-BY 4.0): https://storage.googleapis.com/teow2016/Ecoregions2017.zip ⚠️ · Visor: https://ecoregions2017.appspot.com/ · Earth Engine: `RESOLVE/ECOREGIONS/2017` | 846 ecorregiones, 14 biomas. Estratos de HAR-01 |
| **MCD12Q1 v6.1** (cobertura del suelo, 500 m, anual) | DOI: https://doi.org/10.5067/MODIS/MCD12Q1.061 · Archivos: `https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-public/MCD12Q1.061/` · Recortes por región: https://appeears.earthdatacloud.nasa.gov/ | Clase urbana = IGBP 13 (`LC_Type1`). Incluye máscara de tierra/agua (`LW`). ⚠️ El productor pide **cautela para 2021 en adelante** (AUX-03) |
| GHSL (zonas urbanas, alternativa) | https://human-settlement.emergency.copernicus.eu/ ⚠️ | Alternativa a MCD12Q1 para la máscara urbana después de 2021 |
| **Volcanes · Smithsonian GVP** (Volcanoes of the World v5.4.0, 7-ago-2026) | Base de datos: https://volcano.si.edu/ · DOI: https://doi.org/10.5479/si.GVP.VOTW5-2026.5.4 · WFS (GeoJSON): `https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=json` ⚠️ | Citar la versión y la fecha de descarga |
| **MCD64A1 v6.1** (área quemada, opcional) | DOI: https://doi.org/10.5067/MODIS/MCD64A1.061 · `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD64A1` | Validación externa (HAR-06) |
| **MOD14CMQ / MYD14CMQ** (grilla de 0,25°, mensual, opcional) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/Mx14CMQ` | Nubosidad y observabilidad (GAP-05) |
| Zonas horarias IANA | Releases: https://github.com/evansiroky/timezone-boundary-builder/releases → `timezones-with-oceans.geojson.zip` | Fecha local en la API (licencia ODbL, datos de OSM) |
| Repositorios LP DAAC / LAADS | https://lpdaac.usgs.gov/ · https://ladsweb.modaps.eosdis.nasa.gov/ | Productos MODIS de tierra y de nivel 1 |

---

## 3. Estrategia de descarga recomendada

| Necesidad | Fuente | Frecuencia |
|---|---|---|
| Histórico MODIS de la región (2000-11 → último estándar) | Herramienta de descarga del archivo (JSON/CSV) o resúmenes por país | Una vez + reproceso anual |
| Histórico VIIRS S-NPP (2012-01-20 → 2026-11-02) | Herramienta de descarga del archivo (`VIIRS_SNPP_SP`) | Una vez (la serie ya está cerrada) |
| Histórico VIIRS NOAA-20 (2018-04 →) | Herramienta de descarga del archivo o API `VIIRS_NOAA20_SP` | Una vez + incremental |
| Recientes (NRT) | API `area` con `MODIS_NRT`, `VIIRS_NOAA20_NRT` y `VIIRS_NOAA21_NRT` | Diaria |
| Reemplazo de NRT por estándar | API `area` con fecha, `_SP`, guiada por `data_availability` | Semanal |
| Conteos diarios globales (huecos) | MCD14ML (SFTP de UMD) + archivos diarios de nrt3 + `missing_data` | Mensual / diaria |
