# NINA · versión 0.3 · La memoria del fuego

Atlas mundial con CesiumJS, interfaz React/TypeScript, API FastAPI y consultas DuckDB. Usa datos NASA FIRMS reales y cartografía NASA GIBS. La selección de territorio y período conecta el visor, el calendario, la comparación y la evidencia. [Estado mundial de 0.3](docs/ESTADO_MUNDIAL.md), [alcance y procesamiento](docs/ALCANCE_MUNDIAL.md).

Proyecto para el **NASA Space Apps Challenge**: armonizar las detecciones de fuego MODIS y VIIRS para responder si una temporada de incendios es realmente inusual.

## Abrir la aplicación

En Windows, con Python 3.14 y Node.js 22, desde la raíz del repositorio:

```powershell
.\setup-nina.ps1
.\start-nina.ps1
```

Abrir **http://127.0.0.1:8000**. Documentación interactiva de la API: **http://127.0.0.1:8000/docs**. Detener con Ctrl+C. Usar un solo proceso de servidor, porque la base DuckDB se escribe desde ese proceso.

Para descargar además el histórico público de Perú: detener el servidor y ejecutar `.\setup-nina.ps1 -DownloadData`.

Si la política local no permite scripts PowerShell, los comandos equivalentes son:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd web
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe scripts/bootstrap_data.py
.\.venv\Scripts\python.exe -m nina.ingest
.\.venv\Scripts\python.exe -m nina.science
```

Alternativa con Docker: `docker compose up --build` (monta `data/`; no se declara probada).

El descargador usa el índice real publicado por FIRMS, comprueba tamaño y SHA-256 y reanuda por archivo. Las importaciones son idempotentes. No descargar ni importar desde otra instancia mientras el servidor esté atendiendo escrituras: usar la interfaz de importación/actualización o detenerlo primero.

## Datos locales

| Ruta | Contenido | En Git |
|---|---|---|
| `source/` | Todos los originales FIRMS. En la raíz, los estáticos del equipo (`fire_archive_*.json`, `fire_nrt_*.json`, `*.csv`, ZIP): entrada por defecto de `scripts/import_global.py`, como ámbito mundial (`NINA_SOURCE_DIR`) | No |
| `source/downloads/` | Lo que llega por la API de FIRMS (`/api/acquisitions`, `/api/sync`), el histórico de Perú (`bootstrap_data.py`) y los CSV subidos desde la interfaz. Va en una subcarpeta porque son ámbitos por área: así no se reimportan como mundiales | No |
| `data/` | Derivados: base `nina.duckdb`, Parquet, cachés, modelos y exportaciones (`NINA_DATA_DIR`) | Solo `data/boundaries/` |
| `.env` | Credenciales y configuración local (copiar de `.env.example`) | No |

Importar el archivo mundial del equipo desde `source/` (con el servidor detenido o sobre una base de preparación):

```powershell
.\.venv\Scripts\python.exe -u scripts/import_global.py --data-dir data/world-build --start-year 2025 --end-year 2026
.\.venv\Scripts\python.exe -u scripts/verify_world.py --data-dir data/world-build --refresh-parquet
```

## Qué funciona

- Globo mundial 3D y vista 2D, teselas reales NASA GIBS con caché local y una imagen de referencia disponible sin conexión.
- Selección de países de referencia, todo el Perú, sus divisiones, coordenadas WGS84 y polígonos dibujados. Países: Natural Earth 110m; selección generalizada, no certificación de límites oficiales.
- Comparación MODIS Aqua/VIIRS en una escena con cámara y período compartidos. Las observaciones originales se separan por color y forma; el deslizador funciona con teclado.
- Histórico mensual por instrumento y plataforma, día/noche y tipo de detección.
- Comparación descriptiva contra la mediana del mismo mes de hasta diez años anteriores, con mínimo de cinco años elegibles.
- Distinción entre datos no disponibles, registros parciales y ceros del archivo. Se omite la anomalía de períodos parciales.
- Mapa de coordenadas reales, con muestra determinista cuando hay muchos puntos. La exportación conserva todas las filas de la selección. En móvil, el calendario usa meses por año desplegable.
- Exportación de serie y detecciones CSV, manifiesto JSON, informe TXT y gráfico SVG.
- Calibraciones exploratorias Poisson y factor simple, con años y regiones reservados.
- Experimento de sustitución: revelar la referencia Aqua reservada y el error de una estimación. Caso validado como software sobre archivo peruano, sin declarar armonización científica final.
- Asistente local que consulta los resultados y responde con hechos y referencias. Hay un adaptador opcional para un proveedor LLM compatible; las cifras permanecen bajo control del servidor.
- Descarga mundial reciente y de meses por área mediante MAP_KEY, en trabajos de segundo plano y ventanas de hasta cinco días. Se verifican producto, fechas y ámbito; los meses parciales conservan su estado.
- Importación de CSV FIRMS por ámbito geográfico y reconciliación espacial de productos estándar/provisionales. Las lecturas y exportaciones conservan una revisión consistente durante la ingesta local.
- Recorrido guiado para presentar el problema, comparar observadores y revisar un experimento real; enlaces compartibles con configuración del análisis.

## Archivo mundial actual

La base activa tiene **59.440.077 observaciones**, después de incorporar nueve archivos mundiales del equipo. El período elegido es **2025–2026**: los nuevos originales contienen datos desde el 5 de noviembre de 2025 hasta el 13 de noviembre de 2026 según producto, y se conserva la instantánea mundial del 14 de noviembre previamente descargada. [Cifras por fuente y consultas verificadas](docs/ESTADO_MUNDIAL.md).

El procesamiento no se limita a Perú. El mapa, el calendario, la comparación y las exportaciones consultan esta base mundial. El histórico peruano anterior sigue disponible como conjunto regional. Los originales, la base y Parquet permanecen fuera de Git.

## Datos incorporados en la entrega anterior 0.2

La versión 0.2 contiene **2.108.030 detecciones únicas**, procedentes de **57 archivos incorporados** y **169.096.847 bytes de CSV**:

| Ámbito del archivo | Ventana incorporada | Archivos | Filas nuevas |
|---|---|---|---|
| Perú | 2000–2025, según instrumento | 48 | 2.034.899 |
| Mundial | 14-nov-2026, instantánea NRT | 3 | 49.410 |
| Rectángulo que contiene Australia | Septiembre de 2025, MODIS SP | 6 | 23.721 |

La selección exacta de Australia con la geometría Natural Earth contiene **12.934 observaciones Aqua** en septiembre de 2025. Los archivos descargados también incluyen Terra y los registros del rectángulo envolvente que quedan fuera de la geometría del país; no se confunden esos totales.

**El histórico mundial completo todavía no está descargado.** Se puede ampliar por mes/área desde Fuentes. El globo ofrece navegación mundial y muestra las ventanas efectivamente incorporadas; no convierte huecos en cero ni extrapola el modelo peruano al mundo.

El subconjunto anual peruano conserva sus **48 archivos y 163.067.831 bytes**:

| Fuente | Filas únicas cargadas | Años publicados descargados |
|---|---|---|
| MODIS Terra + Aqua | 358.529 | 2000–2025 |
| VIIRS S-NPP | 1.047.073 | 2012–2025 |
| VIIRS NOAA-20 | 629.297 | 2018–2025 |

El archivo anual peruano comienza el 1-nov-2000 y termina el 31-dic-2025. NOAA-21 y 2026 ya se incorporaron por la API mundial, no por ese índice anual. Las ventanas estándar y NRT se mantienen identificadas.

Los límites proceden de una versión identificada de geoBoundaries gbOpen, fuente Wikimedia Commons, representación de 2008 y licencia Public Domain indicada en el metadato. El conjunto contiene 26 divisiones y no equivale a una certificación de límites administrativos actuales del Estado peruano. Hay **5.452 detecciones** del archivo nacional sin asignación a esa geometría; se conservan en el total nacional.

El inventario, hashes y fuentes están en `data/inventory.json`, `data/processed/*.json` y `data/boundaries/provenance.json`. Los archivos Parquet están en `data/processed/observations.parquet`. El tamaño de CSV no incluye base analítica, Parquet, dependencias, cachés ni productos L2.

## Alcance científico de la versión 0.2

Esta es una **versión funcional de observación mundial, adquisición selectiva y calibración exploratoria peruana**. La armonización con control de nubes, exposición y geometría **todavía no está validada**. No se muestra un porcentaje de cobertura ni un intervalo inventado. La extensión geográfica del visor no amplía automáticamente la validez del modelo.

Los modelos del laboratorio usan conteos mensuales de archivo: entrenamiento en 2018–2022, validación en 2023 y prueba en 2024–2025, con regiones reservadas. Solo los meses positivos del instrumento de entrada aportan pares; no se ha reconstruido el conjunto de oportunidades válidas. Por eso las métricas de ajuste no prueban recuperación del fuego no observado ni tendencias sin sesgo. La exploración del modelo se limita a divisiones del conjunto y al período 2018–2025; no se aplica a polígonos arbitrarios ni se declara una serie nacional corregida.

Los meses del calendario se agrupan en **UTC** en esta versión. No se ofrece todavía selección del calendario civil `America/Lima`. Las anomalías son descripciones de conteos observados de una misma selección; no implican significancia estadística ni riesgo de incendio futuro.

La etapa pendiente del reto requiere descargar/alinear máscaras y geolocalización, construir oportunidades válidas y evaluar la armonización a esa escala. `scripts/inventory_l2.py` ya consulta metadatos CMR y guarda muestras identificadas para los productos encontrados; no es un inventario exhaustivo ni un descargador autenticado de los productos científicos. Los huecos no se sustituyen por ceros físicos.

## Credenciales opcionales

Copiar `.env.example` a `.env` y configurar localmente las variables necesarias. Nunca incluir `.env` en Git ni publicar claves.

- `FIRMS_MAP_KEY`: habilita el catálogo, la instantánea mundial de MODIS/NOAA-20/NOAA-21 y la descarga mensual por área. `/api/sync` conserva compatibilidad con el cliente peruano anterior; las rutas nuevas son `/api/acquisitions` y `/api/acquisitions/month`.
- `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`: reservadas para el siguiente paso de descarga científica autenticada; la versión 0.2 no descarga ni procesa L2 automáticamente.
- `NINA_LLM_BASE_URL`, `NINA_LLM_API_KEY`, `NINA_LLM_MODEL`: activan el adaptador de lenguaje. Sin ellas, el asistente conserva respuestas deterministas respaldadas por el análisis. El proveedor opcional solo recibe la pregunta, el rol y el resumen de resultados del análisis seleccionado; no recibe credenciales NASA ni el archivo completo.

Reiniciar el servidor después de cambiar `.env`.

## Verificación y desarrollo

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd web
npm.cmd run build
npm.cmd run dev
```

El CI (`.github/workflows/ci.yml`) ejecuta las pruebas Python y la compilación web.

## Repositorio

| Ruta | Contenido |
|---|---|
| `nina/` | Paquete Python: API FastAPI (`main.py`), ingesta, consultas, calibración exploratoria, asistente |
| `web/` | Interfaz React + Vite + CesiumJS |
| `scripts/` | Descarga, importación, verificación y exportación de OpenAPI |
| `tests/` | Pruebas `pytest` |
| `design/`, `nina-demo.html` | Dirección de diseño y demo estática |
| `openapi.json` | Contrato de la API, generado con `scripts/export_openapi.py` |
| `AGENTS.md` | Reglas para agentes y especificación técnica (estado actual + objetivo de armonización) |
| `WORK_PLAN.md` | Plan de trabajo para 3 personas: roles, propiedad de archivos, fases |
| `docs/` | Estado, arquitectura, fuentes de datos, criterios de aceptación, contrato objetivo, ADRs y `reference/` |

## Aviso

Datos de NASA FIRMS. Por su resolución espacial, FIRMS no recomienda usar estos datos para decisiones tácticas o a escala local: esta herramienta da **contexto histórico**. Ver el [descargo de responsabilidad de FIRMS](https://www.earthdata.nasa.gov/data/tools/firms).
