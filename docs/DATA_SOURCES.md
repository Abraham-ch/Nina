# NINA · Fuentes de datos y estado de preparación

**Estado vigente 0.2:** [ESTADO_V2.md](ESTADO_V2.md). El archivo reúne 2.108.030 observaciones únicas en 57 archivos incorporados: 48 nacionales peruanos, 3 mundiales NRT del 14-nov-2026 y 6 ventanas MODIS SP del rectángulo australiano para septiembre de 2025. Se verificó realmente la disponibilidad FIRMS con MAP_KEY y se ejecutó la adquisición mensual desde la interfaz. El catálogo filtrado, sin credenciales, está en `data/catalog/firms-availability.json`. La cartografía de referencia usa NASA GIBS y Natural Earth 110m. Las credenciales Earthdata están configuradas localmente; la descarga/lectura científica L2 sigue pendiente. Las revisiones 0.1 siguientes conservan el contexto anterior.

**Actualización tras implementar 0.1:** se verificó el índice público `/data/country/yearly_summary_files.txt` utilizado por la página FIRMS, se descargaron sus 48 archivos nacionales y se importaron 2.034.899 detecciones. Los CSV ocupan exactamente 163.067.831 bytes. [Uso de la aplicación](../README.md), [estado actualizado](ESTADO_V1.md) y `data/inventory.json` documentan esta ejecución. Las secciones de revisión documental siguientes conservan el estado anterior donde no hubo una comprobación nueva; el estado vigente de implementación está en `ESTADO_V1.md`.

**Alcance vigente: mundial, con adquisición por área/período y disponibilidad explícita.** El orden de ejecución está en [PLAN_IMPLEMENTACION.md](PLAN_IMPLEMENTACION.md). El histórico mundial completo y la validación científica global no se declaran completados.

> Ubicación actual: `DATA_SOURCES.md`, en la raíz del workspace. El pipeline de observaciones está implementado en `nina/` y `scripts/`. `docs/DATA_SOURCES.md` y `data/sources.yaml` no son rutas utilizadas por la versión 0.1.
> Revisión documental inicial: 13-nov-2026. Posteriormente se descargó e importó el archivo público nacional y se consultaron muestras de metadatos CMR. Las credenciales y descargas autenticadas L2 siguen pendientes.
> ⚠️ indica una ruta o condición pendiente de comprobación. Una URL documentada no equivale a un archivo descargado, leído y validado. Los identificadores ING/HAR/GAP/AUX del borrador son referencias de planificación; no acreditan tareas implementadas.

## Resultado de la revisión

**La versión 0.1 ya tiene un conjunto nacional preparado de detecciones observadas; la armonización científica con oportunidades válidas sigue pendiente.** El recurso de la hackathon facilitado por el equipo enlaza a [NASA FIRMS](https://www.earthdata.nasa.gov/data/tools/firms); es un portal de productos y servicios, no un paquete de entrenamiento o una serie ya armonizada.

El texto de Resources recibido confirma esa fuente central. No establece que todos los auxiliares de este documento sean obligatorios. El acceso automático a la página del reto falló durante la revisión, por lo que no se certifica que el extracto compartido agote todas sus pestañas o futuras incorporaciones.

Correcciones principales: NOAA-21 dispone de fuente estándar en `area` y `data_availability`; el archivo FIRMS de NOAA-21 empieza el 1-mar-2023; las API `area` y `country` documentan límites distintos; se incorporan productos L2 para oportunidades de observación y se aclara qué falta validar. Véanse las secciones 4–6.

## 0. Credenciales necesarias

| Variable de entorno | Para qué | Cómo se obtiene |
|---|---|---|
| `FIRMS_MAP_KEY` | API de FIRMS (32 caracteres hexadecimales) | https://firms.modaps.eosdis.nasa.gov/api/map_key/ |
| Earthdata Login mediante el mecanismo que admita el servicio (p. ej., `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` o `~/.netrc`) | Descargas protegidas y productos científicos L2/auxiliares. Confirmar autenticación por servicio; una MAP_KEY no sustituye Earthdata Login | https://urs.earthdata.nasa.gov/ |
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
| VIIRS NOAA-21 | `VIIRS_NOAA21_NRT` / `VIIRS_NOAA21_SP` | **1-mar-2023 → presente, en el archivo FIRMS** | Ambas fuentes documentadas en `area` y `data_availability`. Consultar fechas efectivas antes de descargar; la página `country` aún no enumera `_SP` |
| Landsat | `LANDSAT_NRT` | 20-jun-2022 → hoy | Excluido del proyecto (solo EE. UU./Canadá) |

Fuentes: [archivo FIRMS](https://firms.modaps.eosdis.nasa.gov/download/), [Area API](https://firms.modaps.eosdis.nasa.gov/api/area/), [disponibilidad](https://firms.modaps.eosdis.nasa.gov/api/data_availability/) y [transición de S-NPP](https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know). Las fechas de esta tabla corresponden al archivo de puntos FIRMS, no necesariamente al comienzo de cada producto L2 ni a todas las variantes NRT/SP.

**Decisión para NINA:** conservar S-NPP para el historial y los experimentos de solapamiento; usar NOAA-20 y NOAA-21 para continuidad reciente, evaluando cada plataforma. El aviso de fin de entrega no elimina el histórico de S-NPP. «Presente» en un catálogo no certifica la disponibilidad del último día.

### 1.2 API REST (requiere `FIRMS_MAP_KEY`)

Base: `https://firms.modaps.eosdis.nasa.gov`

| Servicio | URL | Uso en el proyecto |
|---|---|---|
| Focos por área (lo más reciente) | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}` | Job NRT diario |
| Focos por área desde una fecha | `/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAY_RANGE}/{YYYY-MM-DD}` | Rellenos incrementales y reprocesos de los NRT → estándar |
| Focos por país | `/api/country/csv/{MAP_KEY}/{SOURCE}/{ISO3}/{DAY_RANGE}[/{YYYY-MM-DD}]` | Alternativa a `area` para un país (p. ej., `PER`) |
| Disponibilidad de fechas | `/api/data_availability/csv/{MAP_KEY}/{SOURCE\|ALL}` | Patrón confirmado en la [documentación](https://firms.modaps.eosdis.nasa.gov/api/data_availability/); consulta autenticada pendiente. Fechas de servicio, no cobertura válida de cada AOI |
| Fechas sin datos | [Tabla publicada de missing data](https://firms.modaps.eosdis.nasa.gov/usfs/api/missing_data/) | Documenta días ausentes por satélite/tipo. Endpoint de datos y alcance aplicable a Perú pendientes; no asumir que existe `/api/missing_data/` ni que diagnostica nubosidad local |
| Estado de la MAP_KEY | `/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}` ⚠️ | Consultar el consumo de transacciones |
| Documentación de la API | https://firms.modaps.eosdis.nasa.gov/api/area/ · https://firms.modaps.eosdis.nasa.gov/api/country/ · https://firms.modaps.eosdis.nasa.gov/api/data_availability/ | Separar documentación de rutas que devuelven CSV |

- `AREA` = `oeste,sur,este,norte` en grados decimales (p. ej., Perú ≈ `-81.4,-18.4,-68.6,-0.03`), o `world`.
- **Límites**: 5000 transacciones cada 10 minutos por MAP_KEY. Las solicitudes grandes pueden consumir múltiples transacciones; no asumir una equivalencia fija entre petición y transacción.
  La [API `area`](https://firms.modaps.eosdis.nasa.gov/api/area/) documenta `DAY_RANGE` **1–5**; la [API `country`](https://firms.modaps.eosdis.nasa.gov/api/country/) documenta **1–10**. Configurar y comprobar por endpoint. Para el primer cliente de `area`, usar un máximo de 5; no enviar 10 porque otra API lo permita.
- Los datos **RT** y **URT** (casi en tiempo real) se eliminan cuando se procesan los NRT correspondientes, o pasadas 6 h.

### 1.3 Archivos NRT de acceso directo (ventanas recientes; descarga pendiente de prueba)

Rutas candidatas para respaldo. No se comprobó en esta revisión el HTTP, contenido ni requisito de acceso de cada archivo. Validar redirecciones, cabecera CSV y última adquisición; una página de login devuelta como HTML no es una descarga de datos correcta.

Patrón: `https://firms.modaps.eosdis.nasa.gov/data/active_fire/{carpeta}/{formato}/{PREFIJO}_{Región}_{24h|48h|7d}.{ext}`

| Sensor | Carpeta | Prefijo | Ejemplo (global, 7 días, CSV) |
|---|---|---|---|
| MODIS C6.1 | `modis-c6.1` | `MODIS_C6_1` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_7d.csv |
| NOAA-20 | `noaa-20-viirs-c2` | `J1_VIIRS_C2` | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv |
| NOAA-21 | `noaa-21-viirs-c2` ⚠️ | `J2_VIIRS_C2` ⚠️ | https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_7d.csv ⚠️ |
| S-NPP (congelado) | `suomi-npp-viirs-c2` | `SUOMI_VIIRS_C2` | ya no se actualiza |

- Regiones candidatas: `Global`, `South_America` ⚠️, `Central_America` ⚠️, etc. El borrador mencionaba `J1_VIIRS_C2_Northern_and_Central_Africa_24h.csv`; ese archivo no se volvió a descargar en esta revisión.
- Shapefile: `.../{carpeta}/shapes/zips/{PREFIJO}_{Región}_{periodo}.zip` (p. ej., `.../modis-c6.1/shapes/zips/MODIS_C6_1_Europe_24h.zip`).
- Uso: **respaldo** del job NRT cuando la API falla. No sirven para el histórico.

### 1.4 Archivos de texto diarios (últimos ~2 meses, con Earthdata Login)

- Principal: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS
- Respaldo: https://nrt4.modaps.eosdis.nasa.gov/archive/FIRMS
- Guía: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS/README.pdf
- Uso propuesto: diagnóstico de ingestión reciente. Comprobar retención y acceso; los conteos globales no certifican cobertura de un AOI.

### 1.5 Histórico masivo

| Recurso | URL | Notas |
|---|---|---|
| Herramienta de descarga del archivo | https://firms.modaps.eosdis.nasa.gov/download/ | La página documenta CSV, SHP y JSON, autenticación por Earthdata o código por email y entrega de instrucciones por email. El importador inicial usará CSV; queda pendiente completar una solicitud y validar su archivo real |
| Resúmenes anuales por país (CSV) | https://firms.modaps.eosdis.nasa.gov/country/ | Archivo por país y año. La forma más rápida de cargar el histórico de un país (p. ej., Perú) |
| Índice público de archivos anuales | https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt | Verificado y utilizado por `scripts/bootstrap_data.py`: proporciona nombre, bytes y fecha de actualización. Se descargaron los 48 archivos `*_Peru.csv` publicados al consultar el índice |
| MCD14ML mensual global (MODIS) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD14ML/MCD14ML.YYYYMM.006.03.txt.gz` (o `C61` ⚠️) | Archivos de detecciones para agregar por fecha/plataforma. Ruta, colección y parser pendientes de comprobar contra un archivo real y su guía; un conteo de cero no demuestra por sí solo un fallo de observación |
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
| **Límites administrativos GADM 4.1** | Patrón: `https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_{ISO3}.gpkg` (p. ej., `gadm41_PER.gpkg`). Índice SHP: https://geodata.ucdavis.edu/gadm/gadm4.1/shp/ | La [licencia publicada](https://gadm.org/license.html) permite usos académicos/no comerciales y exige permiso previo para **redistribución o uso comercial**. No incorporar el archivo a una descarga pública o repositorio por defecto; seleccionar una geometría con condiciones adecuadas al uso de NINA |
| Límites oficiales del Perú (INEI/IGN) | Portal de datos abiertos del INEI ⚠️ | Opcional, para tener nombres oficiales |
| **Ecorregiones RESOLVE 2017** | Shapefile (~150 MB, CC-BY 4.0): https://storage.googleapis.com/teow2016/Ecoregions2017.zip ⚠️ · Visor: https://ecoregions2017.appspot.com/ · Earth Engine: `RESOLVE/ECOREGIONS/2017` | 846 ecorregiones, 14 biomas. Estratos de HAR-01 |
| **MCD12Q1 v6.1** (cobertura del suelo, 500 m, anual) | DOI: https://doi.org/10.5067/MODIS/MCD12Q1.061 · [Catálogo del producto](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061) · Recortes por región: https://appeears.earthdatacloud.nasa.gov/ | Clase urbana = IGBP 13 (`LC_Type1`). Incluye `LW`. El catálogo confirma **cautela para 2021 en adelante** por desactualización del entrenamiento. Contexto/estratificación opcional; no reemplaza una máscara de observación de cada pasada |
| GHSL (zonas urbanas, alternativa) | https://human-settlement.emergency.copernicus.eu/ ⚠️ | Alternativa a MCD12Q1 para la máscara urbana después de 2021 |
| **Volcanes · Smithsonian GVP** (Volcanoes of the World v5.4.0, 7-ago-2026) | Base de datos: https://volcano.si.edu/ · DOI: https://doi.org/10.5479/si.GVP.VOTW5-2026.5.4 · WFS (GeoJSON): `https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=json` ⚠️ | Citar la versión y la fecha de descarga |
| **MCD64A1 v6.1** (área quemada, opcional) | DOI: https://doi.org/10.5067/MODIS/MCD64A1.061 · `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/MCD64A1` | Contraste complementario, no verdad equivalente a focos ni evidencia plenamente independiente de MODIS; documentar las dependencias del algoritmo |
| **MOD14CMQ / MYD14CMQ** (grilla de 0,25°, mensual, opcional) | `sftp://fuoco.geog.umd.edu` → `data/MODIS/C6/Mx14CMQ` ⚠️ | Diagnóstico agregado que requiere verificar contenido y versión. Su escala mensual/0,25° no sustituye las oportunidades de observación por celda/pasada del método propuesto |
| Zonas horarias IANA | Releases: https://github.com/evansiroky/timezone-boundary-builder/releases → `timezones-with-oceans.geojson.zip` | Fecha local en la API (licencia ODbL, datos de OSM) |
| Repositorios LP DAAC / LAADS | https://lpdaac.usgs.gov/ · https://ladsweb.modaps.eosdis.nasa.gov/ | Productos MODIS de tierra y de nivel 1 |

Estos auxiliares son elecciones de diseño, no una lista de requisitos de la hackathon. Para el piloto peruano puede declararse `America/Lima` sin incorporar todavía una capa mundial de zonas horarias. No excluir automáticamente focos urbanos, agrícolas o industriales: el enunciado incluye quemas antropogénicas; cualquier filtro debe ser explícito y configurable.

---

## 3. Estrategia de descarga recomendada

| Necesidad | Fuente | Frecuencia |
|---|---|---|
| Histórico MODIS de la región (2000-11 → último estándar) | Archivo CSV o resúmenes por país | Carga inicial + comprobación periódica de revisiones |
| Histórico VIIRS S-NPP (2012-01-20 → 2026-11-02) | Herramienta de descarga del archivo (`VIIRS_SNPP_SP`) | Carga histórica y control de revisiones: terminó la adquisición nueva, pero pueden cambiar versiones o reprocesamientos |
| Histórico VIIRS NOAA-20 (2018-04 →) | Herramienta de descarga del archivo o API `VIIRS_NOAA20_SP` | Una vez + incremental |
| Histórico VIIRS NOAA-21 (archivo FIRMS desde 2023-03-01) | Archivo o `area` con `VIIRS_NOAA21_SP`, tras comprobar disponibilidad | Carga histórica + incremental; no suponer soporte idéntico en `country` |
| Recientes (NRT) | API `area` con `MODIS_NRT`, `VIIRS_NOAA20_NRT` y `VIIRS_NOAA21_NRT` | Diaria |
| Reemplazo de NRT por estándar | Archivo/API, `_SP` y `data_availability`; comprobar rango y volumen | Revisión periódica. Conservar versiones para reproducir resultados; el archivo FIRMS indica un desfase aproximado de 5 meses, no un plazo garantizado |
| Diagnóstico de disponibilidad | Catálogo/tabla de faltantes + ingestión y comprobación de gránulos | Los conteos globales sirven como señal de diagnóstico; no identifican solos la cobertura local ni prueban que un día sin focos sea un hueco |

---

## 4. Datos que faltaban en el catálogo para la armonización propuesta

Los puntos de FIRMS bastan para comenzar a importar detecciones, visualizar mapas y construir conteos brutos por sensor. La arquitectura de NINA añade un objetivo científico: estimar conteos bajo un protocolo de observación común. Para ese método hay que poder reconstruir oportunidades válidas, incluidos ceros observados. Los siguientes productos no son nuevos requisitos atribuidos a NASA; son entradas necesarias para esa metodología.

| Plataforma | Producto de fuego L2 | Formato | Inicio indicado por el catálogo L2 | Uso |
|---|---|---|---|---|
| Terra MODIS | [MOD14 C6.1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod14-061) | HDF4 | 24-feb-2000 | Máscara, calidad y puente del historial anterior a Aqua |
| Aqua MODIS | [MYD14 C6.1](https://www.earthdata.nasa.gov/data/catalog/lpcloud-myd14-061) | HDF4 | 4-jul-2002 | Referencia instrumental inicial propuesta para NINA |
| S-NPP VIIRS | [VNP14IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp14img-002) | NetCDF-4 | 17-ene-2012 | Entrenamiento y evaluación en solapamiento; histórico tras el fin de entrega nueva |
| NOAA-20 VIIRS | [VJ114IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vj114img-002) | NetCDF-4 | 1-ene-2018 | Continuidad y prueba de transferencia entre plataformas |
| NOAA-21 VIIRS | [VJ214IMG C2](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vj214img-002) | NetCDF-4 | 10-feb-2023 | Continuidad reciente y prueba adicional por plataforma |

**Las fechas L2 difieren de las del archivo FIRMS de puntos.** El estado del catálogo o el sufijo `_SP` no garantizan que cualquier día/AOI esté completo: consultar disponibilidad y comprobar los gránulos efectivos.

### Geolocalización, máscaras y calidad

- Añadir explícitamente la geolocalización correspondiente al producto y colección. Los catálogos VIIRS consultados señalan `VNP03MODLL`, `VJ103MODLL` y `VJ203MODLL`, respectivamente. La guía y un gránulo real deben confirmar cómo alinear esos datos con la máscara; no asumir coincidencia de dimensiones entre todas las capas.
- Para MODIS, verificar en la guía la geolocalización incluida y las dependencias necesarias para la máscara completa y la geometría, usando los productos de geolocalización correspondientes cuando proceda. No se fija todavía una ruta binaria no probada.
- Leer códigos de máscara, calidad, relleno, agua, nubes y ausencia de observación según la versión. Una columna de `confidence` de puntos no sustituye esos estados.
- Registrar hora de pasada, geometría de observación y exposición. Si una variable requerida no está en el producto elegido, incorporar su dependencia documentada o limitar el método.
- Distinguir MODIS Terra de Aqua aunque se obtengan desde una fuente combinada de FIRMS. Comparar todas las pasadas matutinas y vespertinas como si fueran equivalentes introduciría un sesgo.
- No sumar plataformas VIIRS de forma que incorporar otro satélite duplique el muestreo objetivo. Preservar plataforma, oportunidad y protocolo de referencia.

Antes de escalar, descargar y leer al menos un par de productos por plataforma/colección objetivo, con su geolocalización, para comprobar driver HDF4/NetCDF, campos, unidades, dimensiones, máscaras y alineación. En 0.1 se verificaron documentación y muestras de metadatos de gránulos CMR mediante `scripts/inventory_l2.py`; no se ha leído todavía el contenido científico L2.

### Auxiliares y contraste

Para la primera versión bastan un AOI bien definido y los datos que exige el protocolo de observación. Ecorregiones, cobertura del suelo, fuentes térmicas persistentes y área quemada se incorporan cuando respondan una pregunta o mejoren una evaluación.

La [ficha RESOLVE](https://developers.google.com/earth-engine/datasets/catalog/RESOLVE_ECOREGIONS_2017) confirma 846 ecorregiones y CC-BY 4.0; eso no verifica por sí solo el enlace ZIP del borrador. La advertencia de MCD12Q1 desde 2021 está confirmada en su [catálogo](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061). Las rutas de GVP, GHSL, SFTP y archivos directos conservan el estado pendiente de prueba donde corresponde; no se realizó una validación de descarga exhaustiva de cada auxiliar.

## 5. Qué tenemos y qué falta

| Elemento | Estado comprobado en el workspace | Criterio para darlo por listo |
|---|---|---|
| Recurso publicado del reto | Texto facilitado por el equipo: enlace a FIRMS | Conservar procedencia; revisar cualquier ampliación del organizador |
| Arquitectura y experiencia | `NINA-arquitectura.md` y `nina-demo.html` existentes | Mantener distinción entre prototipo y resultados reales |
| Inventario de fuentes | Documentación contrastada; rutas candidatas marcadas | Fijar productos, colecciones, disponibilidad y contrato de ingestión |
| Credenciales | No configuradas al entregar 0.1; descarga pública verificada | Consulta autenticada y descarga científica correctas |
| Dataset nacional | 48 CSV, 2.034.899 detecciones únicas, hashes y Parquet | Añadir entradas L2 y datos recientes por otra vía |
| Geometría nacional | geoBoundaries versionado, representación de 2008; 5.452 detecciones sin departamento en esa geometría | Evaluar geometría oficial actual y conservar trazabilidad |
| Pipeline | Descarga reanudable, ingestión, deduplicación técnica y exportación Parquet implementadas | Completar el procesamiento de oportunidades L2 |
| Armonización | Dos modelos Poisson exploratorios ajustados a conteos, con benchmark reservado | Validar el método científico con exposición, máscaras y puentes entre plataformas |
| Calendario real | Aplicación React/API conectada al archivo nacional observado | Incorporar serie armonizada validada y cobertura |
| Asistente | Motor local conectado a análisis reales; adaptador LLM preparado | Probar proveedor externo configurado y evaluar con usuarios |

La publicación de Resources resuelve la incertidumbre sobre la fuente central. No transforma automáticamente un catálogo de URLs en un dataset listo, ni demuestra que un modelo funcione. Tampoco aporta, en el texto recibido, etiquetas de entrenamiento/test o un benchmark oficial ya preparado.

## 6. Cómo seguir: implementación nacional

El [plan de implementación](PLAN_IMPLEMENTACION.md) sustituye la secuencia anterior centrada en un piloto de Madre de Dios. Define 18 tareas con dependencias, responsables propuestos y resultados comprobables.

La primera adquisición se organiza para todo el Perú. Se inventarían las detecciones históricas por fuente/período y los gránulos L2 y dependencias que intersectan el país. Después de probar formatos y accesos con lotes pequeños se ejecuta la descarga nacional reanudable. Los lotes pequeños son una prueba técnica, no una reducción del alcance territorial.

Todavía no se conoce el volumen total de bytes: debe medirse en el inventario y distinguir descarga acumulada, almacenamiento permanente y espacio temporal. Los archivos de pasadas pueden extenderse más allá del país; seleccionar Perú no equivale a recibir automáticamente todos los productos científicos recortados.

El primer hito funcional de consulta y exportación de observaciones reales nacionales ya está implementado. El calendario armonizado requiere oportunidades válidas y evaluación en regiones/períodos reservados de condiciones diversas. El asistente local ya consulta las salidas observadas; la conexión de un proveedor LLM y la fase científica completa conservan sus estados pendientes.
