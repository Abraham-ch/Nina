# Contrato de la API y de la base de datos

> Ubicación en el repo: `apps/api/API_CONTRACT.md`. Versión del contrato: **v0.1.1**.
> Este documento define las dos fronteras entre los equipos:
>
> 1. **Procesamiento → API**: tablas del esquema `serving` en PostGIS (Parte B).
> 2. **API → Web**: endpoints REST `/api/v1` (Parte A).
>
> **Fuente de verdad en código:**
> - API: modelos Pydantic de `apps/api/src/fire_api/models.py` (con `examples`) → `packages/schemas/openapi/openapi.json`
>   y `packages/schemas/src/generated/api.ts`, generados con `pnpm gen:types` (no se editan a mano, AGENTS §3.5).
> - Base de datos: `packages/schemas/db/serving.sql` (DDL).
> - Textos legales: `packages/schemas/legal/firms.json`.
>
> Este documento y esos archivos deben coincidir. Si este documento y AGENTS §12 difieren, **prevalece este contrato**.
> Cualquier cambio sigue el proceso de `WORK_PLAN.md` §6.

---

## Parte A · API REST

### A.1 Convenciones generales

| Tema | Regla |
|---|---|
| Base | `/api/v1` |
| Formato | JSON (UTF-8). Fechas `YYYY-MM-DD`; instantes ISO-8601 en UTC (`2025-11-05T00:00:00Z`) |
| Nombres | `snake_case` en JSON y en parámetros |
| Errores | `application/problem+json` (RFC 9457) con un campo extra `code` (§A.5) |
| Cabeceras de respuesta | `X-Harmonization-Version`, `ETag`, `Cache-Control: public, max-age=3600` (los datos provisionales usan `max-age=600`) |
| Avisos | Los avisos no bloqueantes van en `warnings: [{ "code": "...", "message": "..." }]` dentro del cuerpo |
| Sensor de origen | **No se expone** en los endpoints de análisis. Solo `/meta` y la exportación con `include_source=true` |
| Autenticación | Ninguna en v1 (datos públicos). Límite de uso por IP en el *reverse proxy* |

### A.2 Parámetros comunes de consulta (`QueryParams`)

Los usan `/calendar`, `/timeseries`, `/ranking`, `/hotspots` y `/export/*`.

| Parámetro | Tipo | Requerido | Por defecto | Regla |
|---|---|---|---|---|
| `region_id` | string | uno de los tres | — | Id de `/regions` (p. ej., `PER.15_1`) |
| `bbox` | string `W,S,E,N` | uno de los tres | — | Grados decimales, WGS84 |
| `geometry_id` | string (uuid) | uno de los tres | — | Devuelto por `POST /geometries` (válido 24 h) |
| `start` | date | sí | — | ≥ `2000-11-01` |
| `end` | date | sí | — | ≥ `start`, ≤ última fecha disponible |
| `tz` | string IANA | no | `UTC` | Agrupación por fecha local (p. ej., `America/Lima`) |
| `min_confidence` | `nominal` \| `high` | no | `nominal` | `low` nunca está disponible |
| `daynight` | `all` \| `D` \| `N` | no | `all` | |

Se pasa **exactamente uno** de `region_id`, `bbox` o `geometry_id`. Si no, la respuesta es `422 INVALID_REGION_SPEC`.

### A.3 Endpoints

#### `GET /health`

Sirve para el *liveness* y el *readiness*.

```json
{ "status": "ok", "db": "ok", "cache": "ok", "harmonization_version": "0.3.0" }
```

#### `GET /meta`

Devuelve los metadatos del dataset. La web los usa en el pie de página, en "Detalles del dataset" y para acotar las fechas seleccionables.

```json
{
  "harmonization_version": "0.3.0",
  "generated_at": "2026-11-10T06:00:00Z",
  "date_min": "2000-11-01",
  "date_max": "2026-11-13",
  "provisional_from": "2026-06-30",
  "climatology_years": [2001, 2025],
  "sensors": [
    { "sensor": "modis_terra", "first_date": "2000-11-01", "last_date": "2026-11-13", "status": "active" },
    { "sensor": "viirs_snpp", "first_date": "2012-01-20", "last_date": "2026-11-02", "status": "end_of_mission" }
  ],
  "known_gaps": [ { "start": "2020-08-16", "end": "2020-09-02", "scope": "aqua", "reason": "known_outage" } ],
  "citation": { "text": "...", "dois": ["10.5067/FIRMS/MODIS/MCD14ML", "..."] },
  "disclaimer": { "es": "...", "en": "..." }
}
```

`citation` y `disclaimer` se leen de `packages/schemas/legal/firms.json` (no de la base de datos), igual que en la web.

#### `GET /regions`

Busca regiones administrativas.

| Parámetro | Tipo | Por defecto |
|---|---|---|
| `q` | string (búsqueda sin tildes ni mayúsculas) | — |
| `country` | ISO3 | — |
| `level` | 0–3 | — |
| `limit` | 1–100 | 20 |

```json
{
  "items": [
    { "region_id": "PER.15_1", "name": "Lima", "level": 1, "country": "PER",
      "parent_id": "PER", "bbox": [-77.9, -13.3, -75.5, -10.3], "area_km2": 34802 }
  ]
}
```

#### `GET /regions/{region_id}`

Devuelve una región con su geometría simplificada.

| Parámetro | Tipo | Por defecto |
|---|---|---|
| `simplify` | metros | `500` |

Responde con un GeoJSON `Feature` cuyas `properties` son las mismas de un ítem de `/regions`. Si no existe: `404 REGION_NOT_FOUND`.

#### `POST /geometries`

Sube un área dibujada o un archivo del usuario y devuelve un `geometry_id` reutilizable.

- **Entrada:** `application/geo+json` (un Feature o una FeatureCollection de polígonos) o `multipart/form-data` con `file` (un `.zip` de Shapefile o un `.geojson`, de 10 MB como máximo).
- **Proceso:** reproyecta a EPSG:4326, corrige la geometría (`make_valid`) y une todos los polígonos en un multipolígono.

```json
{ "geometry_id": "8f0c…", "area_km2": 1532.4, "bbox": [-76.1, -12.3, -75.7, -11.9],
  "expires_at": "2026-11-15T09:00:00Z", "warnings": [] }
```

Errores: `422 INVALID_GEOMETRY`, `413 FILE_TOO_LARGE`, `422 AREA_TOO_LARGE` (si supera `MAX_AREA_KM2`).

#### `GET /calendar`

Matriz año × mes de la región. Es la vista principal de la app.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `metric` | `hotspots` \| `active_cells` | `hotspots` |

```json
{
  "query": { "region_id": "PER.15_1", "start": "2001-01-01", "end": "2026-10-31", "tz": "UTC",
             "min_confidence": "nominal", "daynight": "all", "metric": "hotspots" },
  "harmonization_version": "0.3.0",
  "climatology_years": [2001, 2025],
  "scale": { "count_breaks": [0, 3, 10, 30, 100, 300], "anomaly_breaks": [-2, -1, -0.5, 0.5, 1, 2] },
  "cells": [
    { "year": 2024, "month": 9, "value": 412.6, "climatology_median": 180.0,
      "climatology_p10": 60.0, "climatology_p90": 350.0, "anomaly_z": 1.8, "percentile": 96,
      "rank_in_month": 2, "data_gap": false, "partial_coverage": false,
      "is_provisional": false, "low_observability": false }
  ],
  "warnings": []
}
```

Reglas:

- `value` es `null` si `data_gap = true`. **Nunca** se devuelve 0 para un hueco.
- Los meses parcialmente fuera de `[start, end]` se incluyen con `partial_period: true`.
- `anomaly_z` y `percentile` se calculan contra la climatología del mismo mes (`nina.stats`).
- `rank_in_month` es la posición del año entre todos los años para ese mes (1 = el de mayor actividad).

#### `GET /timeseries`

Serie temporal con la banda climatológica.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `freq` | `day` \| `week` \| `month` | `month` |
| `metric` | `hotspots` \| `active_cells` | `hotspots` |
| `compare_years` | lista de años separados por coma (máx. 5) | — |

```json
{
  "query": { "...": "..." },
  "freq": "week",
  "points": [
    { "period_start": "2024-09-02", "value": 88.1, "climatology_median": 41.0,
      "climatology_p10": 9.0, "climatology_p90": 95.0,
      "data_gap": false, "is_provisional": false }
  ],
  "compare": [ { "year": 2023, "points": [ { "period_start": "2023-09-04", "value": 30.2 } ] } ],
  "warnings": [ { "code": "SAMPLING_BIAS", "message": "Agregaciones menores de 8 días tienen sesgo de muestreo." } ]
}
```

`freq=day` **siempre** incluye el aviso `SAMPLING_BIAS` y **no** devuelve los campos de climatología (SAMP-01).

#### `GET /ranking`

Años ordenados por actividad.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `months` | lista `1–12` (temporada; p. ej., `7,8,9,10`) | todos |
| `top` | 1–30 | 10 |

```json
{ "items": [ { "year": 2024, "value": 2310.4, "anomaly_z": 2.1, "excluded": false } ],
  "excluded_years": [ { "year": 2002, "reason": "partial_coverage" } ] }
```

#### `GET /hotspots`

Focos individuales de la consulta, para el mapa y para inspección.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `limit` | 1–5000 | 1000 |
| `cursor` | string opaco | — |

La respuesta es una GeoJSON `FeatureCollection` más `next_cursor`. Cada feature trae
`hotspot_id`, `acq_datetime_utc`, `frp_mw`, `confidence_class`, `daynight` e `is_provisional`.

Para mostrar muchos puntos, la web usa las **teselas vectoriales** (§A.4), no este endpoint.

#### `GET /export/hotspots`

Descarga de los focos de la consulta.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `format` | `csv` \| `zip` | `zip` |
| `include_source` | bool | `false` |

- `csv`: `text/csv` en *streaming*, UTF-8 con BOM, con las columnas de AGENTS §12.1.
- `zip`: incluye `hotspots.csv` y `LEEME.txt` (cita, DOI, aviso, filtros usados y versión).
- Límite: `EXPORT_MAX_ROWS` (por defecto 1 000 000). Si se supera: `413 EXPORT_TOO_LARGE`, con el conteo estimado en `detail`.

#### `GET /export/calendar`

Descarga la matriz de `/calendar`.

| Parámetro extra | Tipo | Por defecto |
|---|---|---|
| `format` | `csv` \| `zip` | `csv` |
| `metric` | `hotspots` \| `active_cells` | `hotspots` |

Columnas: `year, month, value, climatology_median, climatology_p10, climatology_p90, anomaly_z, percentile, data_gap, partial_coverage, is_provisional`.

### A.4 Teselas vectoriales (fuera de FastAPI)

| Recurso | URL | Dueño |
|---|---|---|
| Focos | `{VITE_TILES_URL}/serving.v_hotspots_tiles/{z}/{x}/{y}` (Martin) | API (configuración) + Procesamiento (vista) |

- Atributos: `hotspot_id`, `date` (entero `YYYYMMDD`), `frp_mw`, `confidence_class`.
- La web filtra por fecha en el cliente con expresiones de MapLibre.

### A.5 Errores

```json
{ "type": "https://fire-calendar/errors/area-too-large", "title": "Área demasiado grande",
  "status": 422, "code": "AREA_TOO_LARGE", "detail": "El área (812 000 km²) supera el máximo (500 000 km²)." }
```

| `code` | HTTP | Cuándo |
|---|---|---|
| `INVALID_REGION_SPEC` | 422 | Ninguno, o más de uno, de `region_id`, `bbox` y `geometry_id` |
| `REGION_NOT_FOUND` | 404 | `region_id` inexistente |
| `GEOMETRY_EXPIRED` | 410 | `geometry_id` vencido |
| `INVALID_GEOMETRY` | 422 | Geometría o archivo no válido |
| `AREA_TOO_LARGE` | 422 | Área > `MAX_AREA_KM2` |
| `INVALID_DATE_RANGE` | 422 | `start > end`, o fuera de `[date_min, date_max]` |
| `INVALID_PARAMETER` | 422 | Otro parámetro fuera de dominio |
| `FILE_TOO_LARGE` | 413 | Subida > 10 MB |
| `EXPORT_TOO_LARGE` | 413 | Exportación > `EXPORT_MAX_ROWS` |
| `INTERNAL_ERROR` | 500 | Error no controlado (se registra con un `request_id`) |

Códigos de **aviso** (`warnings`, no son errores): `SAMPLING_BIAS`, `PROVISIONAL_DATA`, `PARTIAL_COVERAGE`, `DATA_GAPS`, `GEOMETRY_REPAIRED`.

### A.6 Rendimiento esperado (para revisar en la Fase 4)

| Endpoint | p95 objetivo (región ≤ 50 000 km², 25 años) |
|---|---|
| `/calendar` (región administrativa, precalculada) | < 300 ms |
| `/calendar` (geometría libre) | < 2 s |
| `/timeseries?freq=week` | < 2 s |
| `/export/hotspots` (primer byte) | < 1 s |

---

## Parte B · Contrato de base de datos (Procesamiento → API)

**Reglas de propiedad:**

- Procesamiento es dueño del esquema `serving`: escribe el DDL en `packages/schemas/db/serving.sql`, aplica las migraciones en
  `packages/schemas/db/migrations/NNN_*.sql` y carga los datos.
- La API **solo lee** de `serving`. Los objetos propios de la API, si los necesita, van en el esquema `api`, con migraciones
  Alembic en `apps/api/migrations`.

### B.1 Tablas y vistas de `serving`

| Objeto | Grano | Columnas principales | Índices |
|---|---|---|---|
| `serving.cell_day` | `h3_cell × date` | `h3_cell text`, `date date`, `hotspots_equiv real`, `active_equiv real`, `data_gap bool`, `partial_coverage bool`, `is_provisional bool`, `low_observability bool` | PK (`h3_cell`, `date`); BRIN (`date`) |
| `serving.cell_geom` | `h3_cell` | `h3_cell text PK`, `geom geometry(Polygon,4326)`, `centroid geometry(Point,4326)` | GIST (`geom`) |
| `serving.hotspots` | detección | `hotspot_id text PK`, `acq_datetime_utc timestamptz`, `acq_date date`, `geom geometry(Point,4326)`, `h3_cell text`, `frp_mw real`, `confidence_class text`, `daynight char(1)`, `quality_level text`, `is_provisional bool`, `instrument text`, `satellite text` | GIST (`geom`); BRIN (`acq_date`); btree (`h3_cell`, `acq_date`) |
| `serving.region` | región administrativa | `region_id text PK`, `name text`, `name_norm text`, `level smallint`, `country char(3)`, `parent_id text`, `geom geometry(MultiPolygon,4326)`, `area_km2 real` | GIST (`geom`); trigram (`name_norm`) |
| `serving.region_cell` | `region_id × h3_cell` | `region_id`, `h3_cell`, `weight real` (fracción de la celda dentro de la región) | PK (`region_id`, `h3_cell`) |
| `serving.region_month` (vista materializada) | `region_id × year × month × metric` | `value`, `data_gap_days`, `partial_days`, `provisional_days` | PK |
| `serving.global_day_status` | `date` | `data_gap bool`, `partial_coverage bool`, `is_provisional bool`, `sensors text[]` | PK (`date`) |
| `serving.dataset_meta` | 1 fila | `harmonization_version`, `generated_at`, `date_min`, `date_max`, `provisional_from`, `climatology_start`, `climatology_end` | — |
| `serving.sensor_coverage` | `sensor` | `first_date`, `last_date`, `status` | — |
| `serving.known_gaps` | periodo | `start`, `end`, `scope`, `reason` | — |
| `serving.v_hotspots_tiles` | vista | `hotspot_id`, `geom` (EPSG:3857), `date int`, `frp_mw`, `confidence_class` (solo los que pasaron QA) | — |

### B.2 Garantías que da Procesamiento

1. La carga es **atómica por versión**: se escribe en `serving_next` y se intercambia con `serving` en una sola transacción,
   así que la API nunca ve datos a medias.
2. `serving.dataset_meta.harmonization_version` cambia en cada publicación. La API usa ese valor para invalidar la caché.
3. Los valores de `serving.cell_day` ya están armonizados ("equivalente VIIRS") y filtrados por QA.
4. `data_gap = true` implica `hotspots_equiv IS NULL`.
5. Existe un **seed** pequeño y sintético, con el mismo DDL: `packages/schemas/db/seed/seed.sql.gz`. Cubre una región de prueba,
   2001–2025, e incluye a propósito huecos, meses provisionales y cobertura parcial.

### B.3 Lógica compartida

Las fórmulas de climatología, percentil, anomalía y ranking viven **solo** en `nina.stats` (`packages/nina/src/nina/stats.py`), que son funciones
puras sin I/O. La API las importa; no las reimplementa. Procesamiento es dueño del módulo y la API revisa sus cambios.

| Función | Firma (resumen) |
|---|---|
| `monthly_climatology(values_by_year_month, years) -> {month: (median, p10, p90)}` | Excluye los meses con hueco o cobertura parcial > 20 % |
| `anomaly(value, climatology) -> (z, percentile)` | z robusto: `(x - mediana) / (1.4826 · MAD)` |
| `rank_years(values_by_year, months) -> [(year, value, z, excluded)]` | |
| `count_breaks(values) -> list[float]` / `ANOMALY_BREAKS` | Cortes de la escala de color que usa la web |

---

## Historial del contrato

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1.0 | 2026-11-14 | Versión inicial |
| 0.1.1 | 2026-11-14 | Rutas al proyecto actual (`nina`, `apps/api/API_CONTRACT.md`); OpenAPI generado desde `models.py` en lugar de `openapi.yaml` a mano; cita y aviso desde `packages/schemas/legal/` (se quitan de `serving.dataset_meta`) |
