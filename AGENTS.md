# AGENTS.md — Calendario armonizado de actividad de incendios (MODIS + VIIRS)

> Guía para agentes de código (y personas) que trabajan en este repositorio.
> Léela completa antes de modificar código. Si una instrucción de aquí entra en conflicto
> con un `AGENTS.md` más profundo (p. ej. `web/AGENTS.md`), prevalece el más cercano al archivo editado.
>
> **Estado actual vs. objetivo.** El código que funciona es el **MVP NINA 0.3** (raíz del repo: `nina/` + `web/`):
> observaciones FIRMS por instrumento, consultas DuckDB y calibración **exploratoria**. Las secciones §5–§11 describen
> la **armonización objetivo**; donde el MVP y esas secciones difieren en tecnología o estructura, **manda el MVP**
> (§3, §4) y el objetivo se alcanza evolucionando el MVP, no creando una estructura paralela.

---

## 1. Propósito

Construir una **serie temporal coherente de focos de calor (2000 → hoy)** combinando:

- **MODIS C6.1** (Terra/Aqua, ~1 km): serie larga, desde 2000.
- **VIIRS 375 m C2** (S-NPP, NOAA-20, NOAA-21): mayor detalle y continuidad, desde 2012.

y servirla en una **aplicación web** donde el usuario elige **región + rango de fechas** y obtiene:

- un **calendario de actividad** (año × mes, escala de color),
- series temporales, anomalías y ranking de años,
- **descarga CSV** de los focos y de los agregados de la consulta.

El proyecto tiene dos etapas:

| Etapa            | Qué produce                                                                       | Dónde vive                            |
| ---------------- | --------------------------------------------------------------------------------- | ------------------------------------- |
| 1 · Armonización | Dataset armonizado: tras esta etapa **el sensor de origen deja de ser relevante** | `nina/` (ingesta, `science.py`), `scripts/` |
| 2 · App web      | API + frontend (hoy: observaciones por instrumento; objetivo: dataset armonizado)  | `nina/main.py`, `web/`                |

El diagrama `docs/architecture/calendario_incendios_arquitectura.excalidraw` muestra el **diseño original** (monorepo, ya
no vigente). La arquitectura actual está en §4 y en `docs/NINA-arquitectura.md`.

---

## 2. Reglas para agentes (obligatorias)

1. **Nunca** sumes ni concatenes conteos de sensores distintos (MODIS/VIIRS) como si fueran una sola serie sin la
   calibración validada (§10). Las observaciones se muestran siempre identificadas por instrumento/plataforma. La lógica
   específica de sensor (origen, normalización, precedencia) vive en `nina/ingest.py`, `nina/global_ingest.py` y
   `nina/remote.py`; `nina/main.py`, `nina/analytics.py` y `web/` no la reimplementan.
2. **Nunca** se commitean datos: `source/` y `data/` están en `.gitignore` (solo `data/boundaries/` está versionado).
   Los tests crean datos sintéticos pequeños en directorios temporales (ver `tests/`).
3. **Nunca** se descarta en silencio una fila: toda fila rechazada se cuenta y se registra con un motivo
   (`rejected`, `duplicates`, `excluded_files`, `qa_reason`) en el reporte de la importación (§9.4).
4. Todos los tiempos se guardan en **UTC**. La conversión a hora local solo ocurre en la API o la UI.
5. **Hueco ≠ parcial ≠ cero.** Un periodo sin datos nunca se devuelve ni se pinta como 0 focos (§5.4).
6. Cualquier cambio en el **método de calibración/armonización** (`nina/science.py`, filtros, grilla) requiere un ADR en
   `docs/adr/` y subir la versión.
7. Cambios en la API (`nina/main.py` y modelos de `nina/analytics.py`) → regenerar `openapi.json` con
   `scripts/export_openapi.py` y actualizar `web/src/types.ts` / `web/src/api.ts` en el mismo PR.
8. Mantén el **aviso legal y la cita de FIRMS** (§11) en la UI y en toda exportación.
9. **Un solo proceso escribe la base DuckDB** (`data/nina.duckdb`): no ejecutes importaciones contra la base que usa el
   servidor; usa `--data-dir data/<staging>` o detén el servidor.
10. Antes de terminar una tarea: `.\.venv\Scripts\python.exe -m pytest -q` y `npm.cmd --prefix web run build`.
    No entregues con pruebas o compilación en rojo.
11. Los cambios de procesamiento (`nina/ingest.py`, `global_ingest.py`, `science.py`, `scripts/`) se contrastan con
    **`docs/ACCEPTANCE_CRITERIA.md`**; los criterios no implementados se anotan como `pendiente`, nunca como cumplidos.

---

## 3. Estructura y configuración del repositorio

Un solo proyecto (no hay monorepo pnpm/turbo/uv): **Python 3.14 + pip** para el servidor y **Node 22 + npm** para la
interfaz. FastAPI sirve la API y también la interfaz compilada (`web/dist/`).

### 3.1 Árbol de carpetas

```
Nina/
├── nina/                     # paquete Python (servidor + procesamiento)
│   ├── main.py               # FastAPI: rutas /api/*, sirve web/dist
│   ├── config.py             # ROOT, .env, NINA_DATA_DIR → data/
│   ├── store.py              # DuckDB: esquema (observations, batches, analyses…), bloqueo y lecturas atómicas
│   ├── ingest.py             # importación CSV FIRMS por ámbito (Perú), reconciliación SP/NRT
│   ├── global_ingest.py      # importación mundial JSON/CSV con memoria acotada (excluye Landsat)
│   ├── remote.py             # cliente FIRMS (MAP_KEY) e imágenes GIBS; credenciales solo en servidor
│   ├── analytics.py          # análisis: calendario, comparación, evidencia, exportaciones
│   ├── science.py            # calibración exploratoria (Poisson / factor simple)
│   └── assistant.py          # asistente determinista + adaptador LLM opcional
├── web/                      # React + Vite + TS + CesiumJS (npm, package-lock.json)
│   ├── src/                  # App, Globe, Calendar, DataPanel, Dialog, Experiment, api.ts, types.ts, export.ts
│   ├── public/assets/        # países (Natural Earth), atribución, imagen de referencia
│   └── scripts/              # preparación de assets (Cesium, geografía)
├── scripts/                  # bootstrap_data, import_global, sync_global, verify_*, export_openapi, inventory_l2…
├── tests/                    # pytest
├── design/ · nina-demo.html  # dirección de diseño y demo estática
├── docs/                     # estado, arquitectura, fuentes, ACCEPTANCE_CRITERIA, API_CONTRACT (objetivo), adr/, reference/
├── notebooks/                # exploración; nada aquí lo importa el servidor
├── data/                     # gitignored salvo boundaries/: derivados (nina.duckdb, processed/, models/, exports/, catalog/, tiles/)
├── source/                   # gitignored: originales. Raíz = estáticos del equipo (fire_archive_*.json, fire_nrt_*.json, *.csv, ZIP)
│   └── downloads/            #   descargas por API FIRMS, histórico de Perú y CSV subidos (config.RAW)
├── openapi.json              # generado con scripts/export_openapi.py (no editar a mano)
├── requirements.txt · requirements.lock.txt · pytest.ini
├── Dockerfile · compose.yaml · .dockerignore
├── setup-nina.ps1 · start-nina.ps1
├── .github/workflows/ci.yml  # pytest + build web
└── .env.example · .gitignore · .editorconfig · .nvmrc (22) · .python-version (3.14)
```

### 3.2 Entorno

- Python: `.venv/` en la raíz (`py -3.14 -m venv .venv`), dependencias fijadas en `requirements.lock.txt`.
  Nueva dependencia → añadirla a `requirements.txt` y regenerar el lock en el mismo PR.
- Web: `web/package-lock.json`. Nueva dependencia → `npm.cmd --prefix web install <pkg>`.
- Configuración: `.env` en la raíz (copiar de `.env.example`). `NINA_DATA_DIR` y `NINA_SOURCE_DIR` se resuelven respecto
  de la raíz. Originales siempre en `source/` (`config.SOURCE`; descargas en `config.RAW` = `source/downloads/`),
  derivados siempre en `data/` (`config.DATA`).

### 3.3 Reglas de organización

- Rutas HTTP en `nina/main.py`; la lógica de consulta en `nina/analytics.py`; el acceso a la base solo por `nina/store.py`.
- Procesamiento e importación en `nina/ingest.py` / `global_ingest.py`; las tareas de consola en `scripts/` solo llaman
  a funciones de `nina/`.
- Archivos de referencia del método objetivo (huecos, ciclo de vida de sensores, esquema de entrada, textos legales):
  `docs/reference/`.
- Archivos generados (`openapi.json`, `web/dist/`) no se editan a mano.
- Tecnologías del plan anterior que **no** se usan (PostGIS, Redis, MinIO, Martin, Prefect, H3, pnpm/Turborepo, uv):
  solo se incorporan con un ADR que justifique el cambio frente al MVP.

---

## 4. Arquitectura

```
 NASA FIRMS (archivo SP + NRT, API MAP_KEY) ──┐      scripts/ (bootstrap, import_global, sync_global)
 source/ (originales del equipo) ─────────────┼────► nina/ingest.py · nina/global_ingest.py · nina/remote.py
 geoBoundaries · Natural Earth · NASA GIBS ───┘                      │
                                                                     ▼
                                              DuckDB data/nina.duckdb  (+ Parquet en data/processed/)
                                                                     │
                                       nina/analytics.py · nina/science.py · nina/assistant.py
                                                                     │
                                              nina/main.py (FastAPI /api/* + web/dist estático)
                                                                     │ JSON · CSV · SVG
                                                                     ▼
                                              web/ (React + CesiumJS) → gestores de emergencias
```

| Componente    | Tecnología                                         | Responsabilidad                                       |
| ------------- | -------------------------------------------------- | ----------------------------------------------------- |
| Procesamiento | Python 3.14, DuckDB, NumPy/SciPy, Shapely          | Ingesta, normalización, reconciliación SP/NRT, §6–§10 |
| Base de datos | DuckDB (archivo local) + Parquet                   | Observaciones, lotes, análisis, trabajos              |
| API           | FastAPI + Uvicorn                                  | Rutas `/api/*` (§12); un solo proceso escribe la base |
| Frontend      | React + Vite + TS + CesiumJS                       | §13                                                   |
| Despliegue    | Local (`start-nina.ps1`) o Docker (`compose.yaml`) |                                                       |
| CI            | GitHub Actions                                     | pytest + compilación web                              |

---

## 5. Fuentes de datos (NASA FIRMS)

### 5.1 Nomenclatura de descargas

Cada instrumento llega en un ZIP independiente, cuyo nombre identifica el origen:

| Prefijo de ZIP        | Instrumento / satélite              | Uso en el proyecto                                 |
| --------------------- | ----------------------------------- | -------------------------------------------------- |
| `DL_FIRE_M-C61_<id>`  | MODIS Collection 6.1 (Terra + Aqua) | ✅                                                 |
| `DL_FIRE_SV-C2_<id>`  | VIIRS 375 m · S-NPP                 | ✅                                                 |
| `DL_FIRE_J1V-C2_<id>` | VIIRS 375 m · NOAA-20 (JPSS-1)      | ✅                                                 |
| `DL_FIRE_J2V-C2_<id>` | VIIRS 375 m · NOAA-21 (JPSS-2)      | ✅                                                 |
| `DL_FIRE_LS_<id>`     | Landsat 30 m                        | ❌ **Excluir** (no forma parte de la armonización) |

Dentro de cada ZIP puede venir CSV (`fire_*.csv` + `Readme.txt`) o Shapefile
(`.dbf .prj .shp .shx .cpg`). **El formato canónico de entrada del pipeline es JSON (§6)**; los
lectores de CSV/SHP convierten a ese formato antes de validar.

### 5.2 Archivos NRT vs. estándar

| Archivo                | Producto    | Calidad        | Notas                                                                           |
| ---------------------- | ----------- | -------------- | ------------------------------------------------------------------------------- |
| `fire_archive_M-C61_*` | MCD14ML     | Estándar (UMD) | Reemplaza al NRT ~3 meses después                                               |
| `fire_nrt_M-C61_*`     | MCD14DL     | NRT (LANCE)    | Provisional                                                                     |
| `fire_archive_SV-C2_*` | VNP14IMGTML | Estándar (UMD) | Reemplaza al NRT ~3 meses después                                               |
| `fire_nrt_SV-C2_*`     | VNP14IMGTDL | NRT            | Provisional                                                                     |
| `fire_nrt_J1V-C2_*`    | VJ114IMGDL  | NRT            | El Readme dice que no hay estándar, pero **la API ya ofrece `VIIRS_NOAA20_SP`** |
| `fire_nrt_J2V-C2_*`    | VJ214IMGDL  | NRT            | Solo NRT (comprobar en `data_availability`)                                     |

> URLs de descarga, API y límites: ver **`docs/DATA_SOURCES.md`**.

Consecuencias que **debes** implementar:

- Detectar `quality_level ∈ {standard, nrt}` desde el **nombre de archivo** (`fire_archive_` / `fire_nrt_`)
  y, como respaldo, desde el campo `version` (contiene `NRT` → `nrt`).
- **Regla de precedencia**: para un mismo `(satellite, acq_date)`, si existen datos estándar, se
  descartan los NRT (`qa_reason = "superseded_by_standard"`).
- `is_provisional` se calcula con la última fecha estándar real de cada sensor, según `/api/data_availability`.
  El retraso es de unos 3 a 5 meses según la fuente. Un job semanal reemplaza NRT por estándar.
- La calidad de NOAA-20 y NOAA-21 se toma de la fuente real (`_SP` = estándar, `_NRT` = nrt), no de una regla fija.
- Una solicitud sin focos devuelve un CSV con solo cabecera o un DBF vacío. **No es un error**:
  regístralo como `0 filas` y continúa.

### 5.3 Cobertura temporal esperada

| Satélite      | Cobertura en FIRMS           | Nota                                                                                          |
| ------------- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| MODIS Terra   | 1-nov-2000 → hoy             | Único paso de la mañana. NASA recomienda migrar desde MODIS                                   |
| MODIS Aqua    | jul-2002 → hoy               |                                                                                               |
| VIIRS S-NPP   | 20-ene-2012 → **2-nov-2026** | ⛔ Sin datos nuevos desde el 2-nov-2026 13:00 UTC. Referencia de la calibración MODIS ↔ VIIRS |
| VIIRS NOAA-20 | 1-abr-2018 → hoy             | **Sensor VIIRS de referencia a partir del 2-nov-2026** (puente S-NPP ↔ NOAA-20, ver SRC-02)   |
| VIIRS NOAA-21 | 17-ene-2024 → hoy            | Respaldo de continuidad (solo NRT)                                                            |

El fin de misión de un satélite se registra en `docs/reference/sensor_lifecycle.yaml` y no cuenta como hueco.

No codifiques estas fechas como verdad: el pipeline calcula la cobertura real
(`min/max(acq_date)` por satélite) y la guarda en la tabla `coverage` (§7.3).

### 5.4 Huecos conocidos en MODIS (Readme de FIRMS + guía de usuario MODIS C6/C6.1)

| Periodo                                        | Situación                                             | Fuente      |
| ---------------------------------------------- | ----------------------------------------------------- | ----------- |
| antes del 2000-11-01 (Terra)                   | Fallas de hardware y calibración: **excluir**         | Guía §7.2.1 |
| septiembre de 2000 (Terra)                     | Instrumento inoperativo                               | Guía §8.3.3 |
| finales de junio → inicios de julio de 2001    | Datos faltantes                                       | Readme      |
| 2002 (a lo largo del año)                      | Datos faltantes intermitentes                         | Readme      |
| 2007, desde mediados de agosto                 | Datos faltantes                                       | Readme      |
| 21-abr-2009 (parcial) y 22-abr-2009 (completo) | Datos faltantes                                       | Readme      |
| 16-ago-2020 → 02-sep-2020 (Aqua)               | Falla del FMU; cobertura limitada a recepción directa | Guía §7.2.4 |

Además, FIRMS advierte que puede haber **datos erróneos**. Implementa:

- `docs/reference/known_gaps.yaml` con esos periodos (fechas exactas a confirmar con el
  conteo diario real; marca como hueco cualquier día con 0 detecciones globales del satélite).
- En los agregados, un día/mes sin datos se marca `data_gap = true`. **No es lo mismo que 0 focos.**
  La UI debe mostrarlo con trama o en gris, nunca como "sin actividad".
- Detección de anomalías de calidad: días cuyo conteo global se aleje más de 5 desviaciones robustas
  (MAD) de la mediana móvil de 31 días → `qa_flag = "suspicious_day"` en el reporte (no se borran).

### 5.5 Proyección

Toda la entrada viene en **WGS84 geográfico (EPSG:4326)**. Se almacena en EPSG:4326; los cálculos
de área usan una proyección de igual área (EPSG:6933) o H3.

---

## 6. Contrato de entrada: JSON (array de objetos)

El pipeline acepta **un archivo `.json` cuyo contenido es un array de objetos**, un objeto por foco.
Ejemplo real (MODIS, estándar):

```json
[
    {
        "latitude": -26.9523,
        "longitude": 32.6844,
        "acq_date": "2025-11-05",
        "acq_time": "0000",
        "scan": 2.5,
        "confidence": "48",
        "daynight": "N",
        "bright_t31": 287,
        "track": 1.5,
        "type": "0",
        "frp": 24.9,
        "instrument": "MODIS",
        "version": "61.03",
        "satellite": "Aqua",
        "brightness": 302.3
    }
]
```

Ejemplo VIIRS (mismo contrato; cambian los campos de brillo y la confianza):

```json
[
    {
        "latitude": -12.0464,
        "longitude": -77.0428,
        "acq_date": "2025-11-05",
        "acq_time": "0618",
        "scan": 0.39,
        "track": 0.36,
        "confidence": "n",
        "daynight": "N",
        "bright_ti4": 330.1,
        "bright_ti5": 290.4,
        "frp": 3.2,
        "instrument": "VIIRS",
        "version": "2.0NRT",
        "satellite": "N"
    }
]
```

### 6.1 Campos

Los tipos son **tal como llegan** (ojo: varios numéricos llegan como _string_).

| Campo        | Tipo crudo           | MODIS                                 | VIIRS                                       | Descripción / validación                                                                                                                                 |
| ------------ | -------------------- | ------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `latitude`   | number               | ✅                                    | ✅                                          | Centro del píxel. `-90 ≤ lat ≤ 90`                                                                                                                       |
| `longitude`  | number               | ✅                                    | ✅                                          | Centro del píxel. `-180 ≤ lon ≤ 180`                                                                                                                     |
| `acq_date`   | string `YYYY-MM-DD`  | ✅                                    | ✅                                          | Fecha de adquisición en **UTC**                                                                                                                          |
| `acq_time`   | string `HHMM`        | ✅                                    | ✅                                          | Hora **UTC**, con ceros a la izquierda (`"0000"`, `"0618"`). Si llega como número (`618`), rellenar a 4 dígitos                                          |
| `scan`       | number               | ✅                                    | ✅                                          | Tamaño del píxel a lo largo del barrido (km)                                                                                                             |
| `track`      | number               | ✅                                    | ✅                                          | Tamaño del píxel a lo largo de la trayectoria (km)                                                                                                       |
| `confidence` | **string**           | `"0"`–`"100"`                         | `"l"` / `"n"` / `"h"`                       | Ver §9.2                                                                                                                                                 |
| `daynight`   | string               | ✅                                    | ✅                                          | `"D"` día, `"N"` noche                                                                                                                                   |
| `brightness` | number               | ✅                                    | —                                           | MODIS: temperatura de brillo canal 21/22 (K)                                                                                                             |
| `bright_t31` | number               | ✅                                    | —                                           | MODIS: temperatura de brillo canal 31 (K)                                                                                                                |
| `bright_ti4` | number               | —                                     | ✅                                          | VIIRS: brillo I-4 (K). En algunos servicios llega como `brightness`                                                                                      |
| `bright_ti5` | number               | —                                     | ✅                                          | VIIRS: brillo I-5 (K). En algunos servicios llega como `brightness_2`                                                                                    |
| `frp`        | number               | ✅                                    | ✅                                          | Potencia radiativa del fuego (MW). `≥ 0`                                                                                                                 |
| `type`       | **string**, opcional | ✅*                                   | ✅*                                         | `"0"` vegetación presunta · `"1"` volcán activo · `"2"` otra fuente terrestre estática · `"3"` offshore. *Solo en productos **estándar**; ausente en NRT |
| `instrument` | string               | `"MODIS"`                             | `"VIIRS"`                                   |                                                                                                                                                          |
| `version`    | string               | p. ej. `"61.03"`, `"6.1"`, `"6.1NRT"` | p. ej. `"2"`, `"2.0NRT"`                    | Colección/versión. Permite distinguir el origen tras combinar archivos                                                                                   |
| `satellite`  | string               | `"Aqua"`, `"Terra"` (o `"A"`, `"T"`)  | `"N"` (S-NPP), `"N20"`/`"1"`, `"N21"`/`"2"` | Normalizar con el mapa de §7.2                                                                                                                           |

### 6.2 Reglas del validador (`docs/reference/hotspot_input.schema.json`)

- Raíz: `type: array`, `items: object`. Un array vacío `[]` es **válido**.
- Requeridos: `latitude, longitude, acq_date, acq_time, confidence, daynight, frp, instrument, satellite`.
- `additionalProperties: true` (FIRMS puede añadir campos; se conservan en `raw_extra`).
- Por instrumento: si `instrument = "MODIS"` → requiere `brightness`; si `"VIIRS"` → requiere `bright_ti4`
  (o su alias `brightness`).
- Lectura con codificación **UTF-8**; tolera BOM. El `Readme.txt` de FIRMS trae caracteres mal codificados
  (`â€œ`): no dependas de parsear ese archivo.

---

## 7. Esquema normalizado y armonizado

### 7.1 `hotspots_normalized` (salida de la normalización, una fila por detección)

| Columna               | Tipo                                             | Origen / regla                                                                 |
| --------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| `hotspot_id`          | text (PK)                                        | Hash estable de `satellite_norm, acq_datetime_utc, round(lat,4), round(lon,4)` |
| `acq_datetime_utc`    | timestamptz                                      | `acq_date` + `acq_time` (`HHMM`) en UTC                                        |
| `acq_date_utc`        | date                                             |                                                                                |
| `lat`, `lon`          | double                                           |                                                                                |
| `geom`                | geometry(Point, 4326)                            |                                                                                |
| `instrument`          | enum `modis \| viirs`                            |                                                                                |
| `satellite_norm`      | enum `terra \| aqua \| snpp \| noaa20 \| noaa21` | §7.2                                                                           |
| `quality_level`       | enum `standard \| nrt \| rt`                     | §5.2; `rt` = RT/URT provisional (SRC-05)                                       |
| `is_provisional`      | bool                                             | `nrt`/`rt` y fecha posterior a la última fecha estándar del sensor             |
| `confidence_raw`      | text                                             | Valor original                                                                 |
| `confidence_class`    | enum `low \| nominal \| high`                    | §9.2                                                                           |
| `daynight`            | enum `D \| N`                                    |                                                                                |
| `frp_mw`              | double                                           |                                                                                |
| `bt_mir_k`            | double                                           | MODIS `brightness` / VIIRS `bright_ti4`                                        |
| `bt_tir_k`            | double                                           | MODIS `bright_t31` / VIIRS `bright_ti5`                                        |
| `scan_km`, `track_km` | double                                           |                                                                                |
| `hotspot_type`        | smallint null                                    | `type`; `null` si NRT                                                          |
| `version`             | text                                             | Original                                                                       |
| `source_file`         | text                                             | Nombre del archivo de origen                                                   |
| `h3_cell`             | text                                             | Celda H3 en `H3_RES` (§10)                                                     |
| `qa_flags`            | text[]                                           | §9                                                                             |

### 7.2 Normalización de `satellite`

```python
SATELLITE_MAP = {
    "Terra": "terra", "T": "terra",
    "Aqua": "aqua",   "A": "aqua",
    "N": "snpp", "NPP": "snpp", "Suomi NPP": "snpp",
    "N20": "noaa20", "1": "noaa20", "NOAA-20": "noaa20", "J1": "noaa20",
    "N21": "noaa21", "2": "noaa21", "NOAA-21": "noaa21", "J2": "noaa21",
}
```

Un valor fuera del mapa → fila rechazada con `qa_reason = "unknown_satellite"` (y alerta en el reporte).
Si el nombre del archivo (`SV`, `J1V`, `J2V`, `M`) contradice `satellite`, gana el archivo y se añade
`qa_flag = "satellite_mismatch"`.

### 7.3 Tablas objetivo

> Hoy la base es DuckDB (`nina/store.py`: `observations`, `batches`, `analyses`, …). Esta tabla describe el modelo
> objetivo de la armonización; se implementa en DuckDB salvo ADR en contrario.

| Tabla / vista         | Grano                               | Uso                                                               |
| --------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `hotspots`            | detección (solo filas que pasan QA) | Mapa, exportación de focos                                        |
| `cell_day_activity`   | `h3_cell × date × satellite_norm`   | Base de la armonización                                           |
| `harmonized_cell_day` | `h3_cell × date`                    | **Tabla que consume la app** (§10.4)                              |
| `admin_regions`       | polígono                            | Selector de regiones                                              |
| `coverage`            | `satellite_norm`                    | `first_date`, `last_date`, `quality_level`                        |
| `data_gaps`           | `satellite_norm × date`             | Huecos conocidos y detectados                                     |
| `mv_region_month`     | vista materializada                 | Calendarios precalculados para regiones administrativas           |
| `dataset_versions`    | versión                             | `harmonization_version`, fecha de corrida, métricas de validación |

---

## 8. Fechas y tiempo

- Fuente de verdad: `acq_date` + `acq_time` en **UTC** → `acq_datetime_utc`.
- La agregación diaria por defecto usa la **fecha UTC**. La API acepta `tz` (IANA, p. ej. `America/Lima`)
  para reagrupar por fecha local; el calendario mensual casi no cambia, el diario sí.
- Rango global del dataset: desde el primer día con datos de MODIS Terra (≈ nov-2000) hasta el último
  día ingerido. La **climatología** usa por defecto **2001 → último año completo** (2000 está incompleto).
- Periodo de solapamiento para calibrar: **2012-01-20 → último día con datos estándar de S-NPP**.
  Los NRT no se usan para calibrar.
- Meses con `data_gap` o `partial_coverage` en > 20 % de sus días se excluyen de la climatología y del ranking de años.
- **Sesgo de muestreo**: según la guía MODIS, las series con intervalos menores de unos 8 días tienen sesgos graves.
  El calendario es **mensual**; las anomalías y rankings solo se calculan con agregaciones de 8 días o más, y toda
  salida diaria lleva `sampling_bias_warning = true`.

---

## 9. Calidad de datos (QA)

### 9.1 Orden del pipeline de QA

1. **Esquema**: validar contra el JSON Schema (§6.2). Si falla → `qa_reason = "schema_invalid"`.
2. **Rangos**: lat/lon válidos, `frp ≥ 0`, `daynight ∈ {D,N}`, `acq_time` en 0000–2359,
   `acq_date` no futura → `qa_reason = "out_of_range"`.
3. **Origen**: excluir Landsat (`qa_reason = "excluded_instrument"`).
4. **Precedencia estándar > NRT** (§5.2) → `superseded_by_standard`.
5. **Tipo de foco** (solo si existe `type`): conservar `type = 0`. `1, 2, 3` → `non_vegetation_type`.
   Después, para **todos** los focos (incluidos los MODIS con `type = 0`, porque algunas fuentes estáticas no
   vienen marcadas): aplicar `static_source_mask` → celda de ~1 km con detecciones en **≥ 16 días de un mismo
   año calendario** (el criterio de la guía para `type = 2`), zona urbana (MCD12Q1 clase 13), entorno de volcán
   activo o agua.
6. **Confianza** (§9.2): por defecto se excluye `low` → `low_confidence`.
7. **Duplicados**: misma `hotspot_id` → `duplicate`.
8. **Huecos y días sospechosos** (§5.4): no eliminan filas; se registran en `data_gaps` y en el reporte.

### 9.2 Confianza unificada

| Instrumento | Valor crudo | `confidence_class` |
| ----------- | ----------- | ------------------ |
| MODIS       | `0`–`29`    | `low`              |
| MODIS       | `30`–`79`   | `nominal`          |
| MODIS       | `80`–`100`  | `high`             |
| VIIRS       | `l`         | `low`              |
| VIIRS       | `n`         | `nominal`          |
| VIIRS       | `h`         | `high`             |

`confidence` de MODIS llega como string (`"48"`): convertir con `int()`; si no es numérico → `schema_invalid`.
La confianza tiene distinto significado en distintas regiones: no la uses como peso, solo como filtro.

### 9.3 Parámetros objetivo (irán a `nina/config.py`, sobreescribibles por variables de entorno; aún no implementados)

| Parámetro                         | Por defecto                                        |
| --------------------------------- | -------------------------------------------------- |
| `MIN_CONFIDENCE_CLASS`            | `nominal`                                          |
| `KEEP_TYPES`                      | `[0]`                                              |
| `H3_RES`                          | `7` (≈ 5 km²)                                      |
| `PROVISIONAL_DAYS`                | `150` (solo respaldo si falla `data_availability`) |
| `FIRMS_MAX_DAY_RANGE`             | `5`                                                |
| `STATIC_SOURCE_MIN_DAYS_PER_YEAR` | `16`                                               |
| `STATIC_SOURCE_H3_RES`            | `8` (≈ 1 km)                                       |
| `VOLCANO_BUFFER_KM`               | `2`                                                |
| `SERIES_START_DATE`               | `2000-11-01`                                       |
| `MIN_AGG_DAYS_FOR_ANOMALY`        | `8`                                                |

### 9.4 Reporte de QA

Cada corrida escribe `data/reports/qa_<run_id>.json` con: filas leídas por archivo, filas aceptadas,
conteo por `qa_reason`, cobertura por satélite, días con hueco y días sospechosos. El job falla
si `schema_invalid / filas_leídas > 1 %`.

---

## 10. Armonización MODIS ↔ VIIRS

**Problema:** VIIRS (375 m) detecta bastantes más focos que MODIS (1 km) sobre el mismo fuego, así que
concatenar los conteos crudos genera un salto artificial en 2012.

### 10.1 Unidad de conteo

No se cuentan píxeles. Se cuentan **celdas activas**: `active = 1` si la celda H3 (`H3_RES`) tuvo
≥ 1 foco válido ese día. Esto reduce el sesgo por resolución antes de calibrar.

### 10.2 Calibración (en el solapamiento)

1. Construir `cell_day_activity` para MODIS (Terra + Aqua combinados) y VIIRS (S-NPP; NOAA-20/21 solo
   como refuerzo de continuidad después de 2018, nunca para calibrar).
2. Agregar a `estrato × mes`, donde estrato = bioma (o región administrativa nivel 1 si no hay bioma).
3. Ajustar por estrato y mes calendario un modelo `VIIRS_equiv = f(MODIS)`:
    - por defecto: **razón robusta** (mediana de `VIIRS/MODIS` sobre celdas-mes con MODIS > 0);
    - alternativa configurable: regresión de Poisson/NB o _quantile mapping_.
4. Guardar coeficientes en `data/harmonized/calibration_<version>.parquet`.

### 10.3 Validación (gate obligatorio)

- Validación cruzada dejando años fuera (_leave-one-year-out_) en 2012 → último año estándar.
- Métricas por estrato: sesgo relativo, R², RMSE, correlación de Spearman de la estacionalidad mensual.
- **Umbral de aceptación**: |sesgo relativo| ≤ 10 % y Spearman ≥ 0,8 en ≥ 80 % de los estratos con datos.
- Si no se cumple → el flujo falla, no publica y deja el reporte en `data/reports/validation_<version>.json`.
- Opcional: contrastar con área quemada MCD64A1.

### 10.4 Producto final `harmonized_cell_day`

| Columna                 | Descripción                                        |
| ----------------------- | -------------------------------------------------- |
| `h3_cell`, `date`       | Clave                                              |
| `active_cells_equiv`    | 0/1 o fracción, en unidad "equivalente VIIRS"      |
| `hotspot_count_equiv`   | Conteo estimado de focos equivalente VIIRS         |
| `source_mix`            | `modis_only` (2000–2011) · `viirs` · `modis+viirs` |
| `is_provisional`        | Heredado de NRT                                    |
| `data_gap`              | Bool                                               |
| `harmonization_version` | semver                                             |

- 2000–2011: MODIS transformado con la calibración.
- 2012-01-20 → 2026-11-02: VIIRS S-NPP observado (NOAA-20 rellena días sin S-NPP desde 2018).
- 2026-11-02 → hoy: NOAA-20 ajustado con el puente S-NPP ↔ NOAA-20 (NOAA-21 como respaldo).
- La app **no** expone `source_mix` en la UI principal (solo en "Detalles del dataset").

---

## 11. Aviso legal y cita (obligatorio)

FIRMS pide replicar o enlazar su descargo de responsabilidad y su cita al redistribuir los datos.

- **UI**: pie de página permanente con la cita y un enlace al descargo de responsabilidad.
- **Advertencia visible** junto al calendario: por su resolución espacial, FIRMS no recomienda usar estos
  datos para **decisiones tácticas o a escala local**. El calendario es una herramienta de contexto histórico.
- **Exportaciones**: cada CSV incluye un `LEEME.txt` (o descarga ZIP) con la cita de FIRMS, la versión del
  dataset, los filtros usados y la fecha de generación.
- Textos: hoy en la interfaz (`web/src/`) y `web/public/assets/attribution.json`; versión de referencia es/en en
  `docs/reference/firms_legal.json`. Al modificarlos, mantenerlos coherentes en esos lugares.

---

## 12. API (`nina/main.py`)

Fuente de verdad: **`openapi.json`** (generado con `scripts/export_openapi.py`) y `http://127.0.0.1:8000/docs`.
`docs/API_CONTRACT.md` describe el **contrato objetivo** (`/api/v1`) de la versión armonizada; no está implementado.

| Método   | Ruta                                                                       | Uso                                               |
| -------- | -------------------------------------------------------------------------- | ------------------------------------------------- |
| GET      | `/api/health`, `/api/status`                                               | Estado del servicio y de la base                  |
| GET      | `/api/catalog`, `/api/places`, `/api/regions`                              | Catálogo FIRMS, lugares y divisiones              |
| GET      | `/api/imagery/blue-marble/{z}/{x}/{y}.jpg`                                 | Teselas GIBS con caché local                      |
| POST     | `/api/analyses`                                                            | Crea un análisis (territorio + periodo + filtros) |
| GET      | `/api/analyses/{id}`, `…/points`, `…/comparison`, `…/evidence`             | Resultado, puntos, comparación, evidencia         |
| GET      | `/api/analyses/{id}/exports/{kind}`                                        | CSV, manifiesto JSON, informe TXT, SVG            |
| POST     | `/api/assistant`                                                           | Asistente con evidencia                           |
| GET/POST | `/api/models`, `/api/models/train`                                         | Calibraciones exploratorias                       |
| GET      | `/api/jobs`, `/api/jobs/{id}`                                              | Trabajos en segundo plano                         |
| POST     | `/api/import`, `/api/sync`, `/api/acquisitions`, `/api/acquisitions/month` | Importación y adquisición FIRMS                   |
| GET      | `/api/experiments/substitution`                                            | Experimento de sustitución Aqua                   |

### 12.1 CSV de focos exportado (objetivo)

Separador `,`, UTF-8 con BOM (para Excel), fechas ISO-8601:

```
hotspot_id,acq_datetime_utc,acq_date_local,lat,lon,frp_mw,confidence_class,daynight,quality_level,is_provisional,harmonization_version
```

`instrument` y `satellite_norm` solo se incluyen si `?include_source=true`.

---

## 13. Frontend (`web/`)

Hoy: globo 3D/2D con CesiumJS y teselas GIBS (`Globe.tsx`), selección de país/Perú/divisiones/polígono, calendario
mensual (`Calendar.tsx`), comparación MODIS/VIIRS, panel de datos y exportaciones (`export.ts`), asistente (`Dialog.tsx`)
y experimento de sustitución (`Experiment.tsx`). Requisitos que se mantienen al evolucionar:

- **Calendario**: filas = años, columnas = meses; modo conteo (escala secuencial) y modo anomalía (divergente centrada en 0).
    - `data_gap` → celda gris con trama; parcial y provisional distinguibles; nunca un hueco como 0.
    - Tooltip con conteo, mediana de referencia y anomalía. Colores accesibles y leyenda siempre visible.
- **Serie temporal**: en vista diaria, aviso de sesgo de muestreo; meses con cobertura parcial marcados.
- **Descargas**: CSV de focos, CSV del calendario, gráficos SVG/PNG, con cita y aviso (§11).
- Tipos de la API solo en `web/src/types.ts`, alineados con `openapi.json`. TypeScript `strict`.
- Textos en español; `en` opcional.

---

## 14. Comandos

```powershell
# Instalar (Python 3.14 + Node 22)
.\setup-nina.ps1                 # .venv + requirements.lock.txt + npm ci + build web
.\setup-nina.ps1 -DownloadData   # además descarga e importa el histórico público de Perú

# Ejecutar
copy .env.example .env           # y completar valores
.\start-nina.ps1                 # http://127.0.0.1:8000 · API en /docs
npm.cmd --prefix web run dev     # interfaz en modo desarrollo (con el servidor activo)
docker compose up --build        # alternativa con Docker (monta data/)

# Datos (import_global lee source/ por defecto)
.\.venv\Scripts\python.exe -u scripts/import_global.py --data-dir data/world-build --start-year 2025 --end-year 2026
.\.venv\Scripts\python.exe -u scripts/verify_world.py --data-dir data/world-build --refresh-parquet
.\.venv\Scripts\python.exe -m nina.ingest
.\.venv\Scripts\python.exe -m nina.science

# Calidad
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix web run build

# Contrato de la API
.\.venv\Scripts\python.exe scripts/export_openapi.py
```

---

## 15. Pruebas

- `tests/` (pytest): `test_nina.py`, `test_global_ingest.py`, `test_global_queries.py`. Crean bases y archivos
  sintéticos en temporales; nunca leen `source/` ni `data/`.
- Toda corrección de lógica de ingesta, consulta o exportación añade o ajusta una prueba ahí.
- Pruebas objetivo para la armonización (añadir al implementarla):
    - `acq_time "0000"` → `00:00 UTC`; `"618"` y `618` → `06:18 UTC`.
    - `confidence "48"` (MODIS) → `nominal`; `"29"` → `low`; `"h"` (VIIRS) → `high`.
    - Precedencia estándar > NRT para el mismo satélite y día.
    - NRT sin `type` no se rechaza por esquema.
    - Días de hueco conocidos → `data_gap = true`, nunca `count = 0`.
    - Archivo vacío → 0 filas, sin excepción.
    - La armonización conserva el orden de los años (correlación de rangos) en el solapamiento.
- Web: la compilación (`tsc -b && vite build`) es la verificación mínima.

---

## 16. Convenciones

- Python: sigue el estilo del módulo que editas; docstrings y mensajes en español; acceso a la base solo vía `nina/store.py`.
- TypeScript: `strict: true`, sin `any`, componentes funcionales.
- Commits: Conventional Commits (`feat(nina): ...`, `fix(api): ...`, `feat(web): ...`, `docs: ...`).
- Nombres de columnas y tablas en inglés `snake_case`; textos de UI en español.

## 17. Definición de terminado

- [ ] `pytest` y la compilación web en verde.
- [ ] `openapi.json` regenerado y `web/src/types.ts` actualizado si cambió la API.
- [ ] ADR + versión nueva si cambió el método de calibración/armonización.
- [ ] Cita y advertencia de FIRMS presentes en UI y exportaciones.
- [ ] `docs/` actualizado cuando cambia un comportamiento visible para el usuario.

