# AGENTS.md — Calendario armonizado de actividad de incendios (MODIS + VIIRS)

> Guía para agentes de código (y personas) que trabajan en este monorepo.
> Léela completa antes de modificar código. Si una instrucción de aquí entra en conflicto
> con un `AGENTS.md` más profundo (p. ej. `apps/web/AGENTS.md`), prevalece el más cercano al archivo editado.

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
| 1 · Armonización | Dataset armonizado: tras esta etapa **el sensor de origen deja de ser relevante** | `packages/nina`, `pipelines/`         |
| 2 · App web      | API + frontend que consumen **solo** el dataset armonizado                        | `apps/api`, `apps/web`, `packages/ui` |

El diagrama de referencia está en `docs/architecture/calendario_incendios_arquitectura.excalidraw`.

---

## 2. Reglas para agentes (obligatorias)

1. **Nunca** mezcles lógica de sensor (MODIS/VIIRS) en `apps/api` ni en `apps/web`. Esas apps leen el
   esquema armonizado (§7). Toda la lógica específica de sensor vive en `packages/nina`.
2. **Nunca** se commitean datos: `source/` está en `.gitignore`. Para tests usa los _fixtures_ de
   `packages/nina/tests/fixtures/` (pequeños, ≤ 200 filas).
3. **Nunca** se descarta en silencio una fila: toda fila rechazada se cuenta y se registra con un motivo
   (`qa_reason`) en el reporte de QA (§9.4).
4. Todos los tiempos se guardan en **UTC**. La conversión a hora local solo ocurre en la API o la UI.
5. Cualquier cambio en el **método de armonización** (grilla, filtros, modelo de calibración) requiere:
   un ADR en `docs/adr/`, subir `HARMONIZATION_VERSION` (semver) y regenerar el dataset.
6. Cambios en el contrato de la API → regenerar tipos TS (`pnpm gen:types`) en el mismo PR.
7. Mantén el **aviso legal y la cita de FIRMS** (§11) en la UI y en toda exportación.
8. Antes de terminar una tarea: `pnpm turbo run lint test typecheck --filter=...[origin/main]`
   y `uv run pytest` en los paquetes Python afectados. No entregues con tests en rojo.
9. Todo cambio en `packages/nina/` o `pipelines/` debe cumplir
   **`packages/nina/ACCEPTANCE_CRITERIA.md`** y generar el reporte de aceptación que allí se describe.
   Ningún criterio [OBL] puede quedar incumplido.

---

## 3. Estructura y configuración del monorepo

El monorepo combina **dos workspaces** que conviven en la misma raíz:

- **pnpm + Turborepo** para TypeScript (`apps/web`, `packages/ui`, `packages/schemas`, `packages/config`).
- **uv** para Python (`packages/nina`, `apps/api`, `pipelines`), con un único `uv.lock`.

Para que Turborepo pueda orquestar todo (incluido el filtro "solo lo afectado"), **cada paquete Python tiene
también un `package.json` mínimo** cuyos scripts llaman a `uv`. Así `turbo run test` recorre los paquetes TS
y Python, y respeta el grafo de dependencias.

> **Fase inicial:** todavía **no** se crean `pipelines/` ni tests. Lo descrito sobre ellos en este documento
> es el objetivo, no el estado actual: el workspace solo incluye `apps/*` y `packages/*`, y la verificación
> es `pnpm turbo run lint typecheck`. Todos los datos (crudos y derivados) viven en `source/`.

### 3.1 Nombres de paquetes

| Carpeta            | Paquete pnpm      | Paquete Python             | Módulo importable |
| ------------------ | ----------------- | -------------------------- | ----------------- |
| `apps/web`         | `@fire/web`       | —                          | —                 |
| `apps/api`         | `@fire/api`       | `fire-api`                 | `fire_api`        |
| `packages/nina`    | `@fire/nina`      | `nina`                     | `nina`            |
| `packages/schemas` | `@fire/schemas`   | — (Python lee los `.json`) | —                 |
| `packages/ui`      | `@fire/ui`        | —                          | —                 |
| `packages/config`  | `@fire/config`    | —                          | —                 |
| `pipelines`        | `@fire/pipelines` | `fire-pipelines`           | `fire_pipelines`  |

### 3.2 Árbol de carpetas

```
fire-calendar/
├── apps/
│   ├── web/                                # @fire/web · React + Vite + TS
│   │   ├── src/
│   │   │   ├── app/                        # rutas, layout, providers (Router, QueryClient, i18n)
│   │   │   ├── features/                   # una carpeta por funcionalidad, cada una con componentes + hooks + tests
│   │   │   │   ├── region-select/          # dibujar polígono, buscar región, subir GeoJSON/SHP
│   │   │   │   ├── date-range/
│   │   │   │   ├── calendar/               # usa <CalendarHeatmap> de @fire/ui
│   │   │   │   ├── timeseries/
│   │   │   │   ├── map/                    # MapLibre + capa MVT de focos
│   │   │   │   └── export/                 # descargas CSV / PNG
│   │   │   ├── lib/api/                    # cliente HTTP + hooks TanStack Query (tipos de @fire/schemas)
│   │   │   ├── i18n/                       # es.json (por defecto), en.json
│   │   │   └── main.tsx
│   │   ├── tests/e2e/                      # Playwright
│   │   ├── index.html · vite.config.ts · tsconfig.json · package.json
│   │   └── Dockerfile                      # build estático → nginx
│   └── api/                                # @fire/api · fire-api · FastAPI
│       ├── src/fire_api/
│       │   ├── main.py                     # crea la app, monta routers, CORS, middlewares
│       │   ├── settings.py                 # pydantic-settings (lee variables de entorno / .env)
│       │   ├── routers/                    # regions · calendar · timeseries · ranking · hotspots · export · meta
│       │   ├── services/                   # lógica de consulta/agregación (sin HTTP)
│       │   ├── db/                         # engine async, modelos SQLAlchemy/GeoAlchemy2, consultas PostGIS
│       │   ├── cache.py                    # Redis (clave = hash de la consulta + harmonization_version)
│       │   ├── models.py                   # modelos Pydantic de petición/respuesta
│       │   └── export_openapi.py           # vuelca openapi.json para generar tipos TS
│       ├── migrations/                     # Alembic
│       ├── tests/
│       ├── pyproject.toml · package.json · Dockerfile
├── packages/
│   ├── nina/                               # @fire/nina · nina
│   │   ├── src/nina/
│   │   │   ├── config.py                   # parámetros (§9.3), sobreescribibles por entorno
│   │   │   ├── io/                         # ÚNICO lugar con I/O: lectores FIRMS (json/csv/shp), cliente API,
│   │   │   │                               #   SFTP UMD, escritura GeoParquet/S3/PostGIS
│   │   │   ├── ingest.py                   # detección de origen y calidad (ING)
│   │   │   ├── normalize.py                # esquema común (§7.1, SCH)
│   │   │   ├── qa/                         # schema · ranges · precedence · confidence · static_mask · gaps
│   │   │   ├── grid.py                     # H3, celdas activas (§10.1)
│   │   │   ├── calibration.py              # MODIS ↔ VIIRS (HAR)
│   │   │   ├── bridge.py                   # S-NPP ↔ NOAA-20 (SRC-02)
│   │   │   ├── validation.py               # validación dejando un año fuera, umbrales
│   │   │   └── reports.py                  # reportes de QA, validación y aceptación
│   │   ├── known_gaps.yaml · sensor_lifecycle.yaml
│   │   ├── tests/fixtures/                 # JSON pequeños (≤ 200 filas)
│   │   ├── ACCEPTANCE_CRITERIA.md
│   │   └── pyproject.toml · package.json
│   ├── schemas/                            # @fire/schemas · contratos neutrales de lenguaje
│   │   ├── json/                           # hotspot_input.schema.json · qa_report.schema.json
│   │   ├── openapi/openapi.json            # generado desde apps/api (no editar a mano)
│   │   ├── legal/                          # cita FIRMS, DOI, avisos (es/en)
│   │   ├── src/generated/api.ts            # tipos TS generados (no editar a mano)
│   │   ├── src/index.ts
│   │   └── package.json
│   ├── ui/                                 # @fire/ui · componentes React reutilizables
│   │   ├── src/
│   │   │   ├── CalendarHeatmap/            # matriz año × mes, modos conteo/anomalía, gap/provisional
│   │   │   ├── MapView/ · RegionPicker/ · DateRangePicker/ · Legend/
│   │   │   └── scales/                     # escalas de color secuencial/divergente (accesibles)
│   │   └── package.json · tsconfig.json
│   └── config/                             # @fire/config · configuración compartida
│       ├── tsconfig/base.json · tsconfig/react.json
│       ├── eslint/index.js
│       ├── prettier/index.json
│       └── package.json
├── pipelines/                              # @fire/pipelines · fire-pipelines · Prefect 3
│   ├── src/fire_pipelines/
│   │   ├── backfill.py                     # histórico por año
│   │   ├── nrt_daily.py                    # job diario (NRT)
│   │   ├── sp_replace.py                   # semanal: reemplaza NRT por estándar (SRC-06)
│   │   ├── validate.py                     # validación + reporte de aceptación
│   │   └── deployments.py                  # schedules de Prefect
│   └── pyproject.toml · package.json
├── notebooks/                              # exploración; nada aquí es importado por producción
├── source/                                 # gitignored: datos FIRMS crudos (fire_archive_*.json, fire_nrt_*.json, *.csv)
│                                           #   y salidas: interim/ harmonized/ reports/
├── infra/
│   ├── docker-compose.yml                  # Postgres+PostGIS, Redis, MinIO, Martin
│   ├── docker/postgres/init.sql            # CREATE EXTENSION postgis, h3 (si se usa h3-pg)
│   ├── docker/martin.yaml
│   └── terraform/                          # opcional
├── docs/
│   ├── adr/                                # decisiones de arquitectura (0001-*.md)
│   ├── architecture/calendario_incendios_arquitectura.excalidraw
│   ├── DATA_SOURCES.md · methodology.md · user-guide.md
├── .github/workflows/ci.yml · deploy.yml
├── .env.example                            # todas las variables, sin valores secretos
├── .gitignore · .editorconfig · .nvmrc · .python-version
├── package.json · pnpm-workspace.yaml · pnpm-lock.yaml · turbo.json
└── pyproject.toml · uv.lock                # raíz del workspace uv + ruff/mypy/pytest
```

### 3.3 Dependencias permitidas

```
@fire/web           → @fire/ui, @fire/schemas, @fire/config
@fire/ui            → @fire/config
@fire/schemas       → (ninguna)
fire-api            → nina (solo modelos/constantes), lee packages/schemas/json y legal
fire-pipelines      → nina
nina                → (ninguna interna)
```

Prohibido: `apps/*` → `pipelines`, `nina` → `apps/*`, importar desde `notebooks/`, ciclos de cualquier tipo.
Las dependencias internas se declaran **en los dos lados**: `"workspace:*"` en `package.json` (para Turborepo) y
`{ workspace = true }` en `pyproject.toml` (para uv).

### 3.4 Configuración base

**`pnpm-workspace.yaml`**

```yaml
packages:
    - "apps/*"
    - "packages/*"
```

**`package.json` (raíz)**

```json
{
    "name": "fire-calendar",
    "private": true,
    "packageManager": "pnpm@10.0.0",
    "engines": { "node": ">=22" },
    "scripts": {
        "dev": "turbo run dev",
        "build": "turbo run build",
        "lint": "turbo run lint",
        "typecheck": "turbo run typecheck",
        "test": "turbo run test",
        "gen:types": "turbo run gen:types --filter=@fire/schemas",
        "format": "prettier --write ."
    },
    "devDependencies": {
        "turbo": "^2.0.0",
        "typescript": "^5.5.0",
        "prettier": "^3.3.0"
    }
}
```

**`turbo.json`**

```json
{
    "$schema": "https://turbo.build/schema.json",
    "globalDependencies": ["pyproject.toml", "uv.lock", ".env.example"],
    "tasks": {
        "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
        "dev": { "cache": false, "persistent": true },
        "lint": { "dependsOn": ["^build"] },
        "typecheck": { "dependsOn": ["^build"] },
        "test": { "dependsOn": ["^build"], "outputs": ["coverage/**"] },
        "gen:types": {
            "cache": false,
            "outputs": ["openapi/**", "src/generated/**"]
        }
    }
}
```

**`package.json` de un paquete Python** (ejemplo: `packages/nina/package.json`)

```json
{
    "name": "@fire/nina",
    "private": true,
    "scripts": {
        "lint": "uv run ruff check src tests && uv run ruff format --check src tests",
        "typecheck": "uv run mypy src",
        "test": "uv run pytest"
    }
}
```

`apps/api/package.json` y `pipelines/package.json` siguen el mismo patrón y añaden
`"dependencies": { "@fire/nina": "workspace:*" }`. Además, `apps/api` define
`"dev": "uv run fastapi dev src/fire_api/main.py"`.

**`packages/schemas/package.json`** (generación de tipos)

```json
{
    "name": "@fire/schemas",
    "private": true,
    "main": "src/index.ts",
    "scripts": {
        "gen:types": "uv run --package fire-api python -m fire_api.export_openapi openapi/openapi.json && openapi-typescript openapi/openapi.json -o src/generated/api.ts",
        "typecheck": "tsc --noEmit"
    },
    "devDependencies": {
        "openapi-typescript": "^7.0.0",
        "@fire/config": "workspace:*"
    }
}
```

**`pyproject.toml` (raíz del workspace uv)**

```toml
[project]
name = "fire-calendar-workspace"
version = "0.0.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/nina", "apps/api"]

[dependency-groups]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.6", "mypy>=1.11", "pandera>=0.20"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM", "PL"]

[tool.mypy]
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
```

**`pyproject.toml` de un miembro** (ejemplo: `packages/nina/pyproject.toml`)

```toml
[project]
name = "nina"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "polars>=1.0", "pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "shapely>=2.0", "pyogrio>=0.9",
  "h3>=4.0", "duckdb>=1.0", "jsonschema>=4.22", "pyyaml>=6", "httpx>=0.27", "paramiko>=3.4",
  "scipy>=1.13", "statsmodels>=0.14",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Los otros miembros:

- `apps/api` depende de `fastapi[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `geoalchemy2`, `alembic`, `redis`,
  `pydantic-settings` y `nina`.
- `pipelines` depende de `prefect>=3` y `nina`.

Ambos declaran:

```toml
[tool.uv.sources]
nina = { workspace = true }
```

**`packages/config/tsconfig/base.json`**

```json
{
    "compilerOptions": {
        "target": "ES2022",
        "module": "ESNext",
        "moduleResolution": "Bundler",
        "strict": true,
        "noUncheckedIndexedAccess": true,
        "noImplicitOverride": true,
        "exactOptionalPropertyTypes": true,
        "isolatedModules": true,
        "skipLibCheck": true,
        "resolveJsonModule": true
    }
}
```

`react.json` extiende `base.json` y añade `"jsx": "react-jsx"` y `"lib": ["ES2022", "DOM", "DOM.Iterable"]`.
Cada paquete TS tiene su propio `tsconfig.json`, que extiende `@fire/config/tsconfig/react.json`.

**`infra/docker-compose.yml`**

```yaml
services:
    db:
        image: postgis/postgis:16-3.4
        environment:
            POSTGRES_DB: ${POSTGRES_DB:-fire}
            POSTGRES_USER: ${POSTGRES_USER:-fire}
            POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?definir en .env}
        ports: ["5432:5432"]
        volumes:
            - pgdata:/var/lib/postgresql/data
            - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
        healthcheck:
            test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-fire}"]
            interval: 5s
            retries: 10
    redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    minio:
        image: minio/minio
        command: server /data --console-address ":9001"
        environment:
            MINIO_ROOT_USER: ${S3_ACCESS_KEY:-minio}
            MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:?definir en .env}
        ports: ["9000:9000", "9001:9001"]
        volumes: [miniodata:/data]
    martin:
        image: ghcr.io/maplibre/martin
        command: --config /config/martin.yaml
        volumes: [./docker/martin.yaml:/config/martin.yaml:ro]
        depends_on:
            db: { condition: service_healthy }
        ports: ["3000:3000"]
volumes:
    pgdata:
    miniodata:
```

**`.env.example`**

```dotenv
# Base de datos y caché
DATABASE_URL=postgresql+asyncpg://fire:CAMBIAR@localhost:5432/fire
POSTGRES_PASSWORD=CAMBIAR
REDIS_URL=redis://localhost:6379/0
# Almacenamiento de objetos (MinIO local / S3)
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=fire-calendar
S3_ACCESS_KEY=minio
S3_SECRET_KEY=CAMBIAR
# Fuentes de datos (ver docs/DATA_SOURCES.md) — nunca commitear valores reales
FIRMS_MAP_KEY=
EARTHDATA_USERNAME=
EARTHDATA_PASSWORD=
FIRMS_MAX_DAY_RANGE=5
# Armonización / API
HARMONIZATION_VERSION=0.1.0
MAX_AREA_KM2=500000
# Frontend
VITE_API_URL=http://localhost:8000/api/v1
VITE_TILES_URL=http://localhost:3000
```

**`.gitignore`** (mínimo obligatorio)

```gitignore
node_modules/
.turbo/
dist/
coverage/
.venv/
__pycache__/
*.egg-info/
.env
.env.*
!.env.example
source/**
!source/**/.gitkeep
.ipynb_checkpoints/
```

**`.github/workflows/ci.yml`** (resumen)

```yaml
name: ci
on:
    pull_request:
    push:
        branches: [main]
jobs:
    check:
        runs-on: ubuntu-latest
        steps:
            - uses: actions/checkout@v4
              with: { fetch-depth: 0 }
            - uses: pnpm/action-setup@v4
            - uses: actions/setup-node@v4
              with: { node-version-file: .nvmrc, cache: pnpm }
            - uses: astral-sh/setup-uv@v5
            - run: pnpm install --frozen-lockfile
            - run: uv sync --all-packages --frozen
            - name: Lint, tipos y tests (solo lo afectado en PR)
              run: |
                  if [ "${{ github.event_name }}" = "pull_request" ]; then
                    pnpm turbo run lint typecheck test --filter="...[origin/${{ github.base_ref }}]"
                  else
                    pnpm turbo run lint typecheck test
                  fi
```

Los secretos (`FIRMS_MAP_KEY`, credenciales de Earthdata y de despliegue) solo existen como _GitHub Secrets_ (SRC-07).

### 3.5 Reglas de organización

- Código nuevo de procesamiento → `packages/nina`. Los flujos de `pipelines/` solo **orquestan** (llaman funciones,
  programan ejecuciones); no contienen lógica de datos.
- La lógica de consulta de la API vive en `services/`; los `routers/` solo validan la entrada y llaman a servicios.
- Un componente visual que se use en más de una feature, o que pueda reutilizarse, va a `@fire/ui`; lo específico de una
  pantalla se queda en `apps/web/src/features/`.
- Archivos generados (`openapi.json`, `src/generated/`) no se editan a mano: se regeneran con `pnpm gen:types`.
- Nuevas dependencias: TS con `pnpm add <pkg> --filter <paquete>`; Python con `uv add <pkg> --package <paquete>`.
  Nunca instalar en la raíz salvo herramientas de desarrollo comunes.

---

## 4. Arquitectura

```
 NASA FIRMS (archivo + NRT) ─┐
 Límites administrativos ────┤        ┌──────────── pipelines/ (Prefect) ─────────────┐
 (GADM / INEI / IGN)         └──────► │ packages/nina                                  │
                                      │ ingesta → QA → normalización → grilla H3 →     │
                                      │ calibración MODIS↔VIIRS → validación → export  │
                                      └───────────────┬───────────────────────┬────────┘
                                                      ▼                       ▼
                                   S3/MinIO: GeoParquet (raw, interim,   PostgreSQL + PostGIS
                                   harmonized, particionado año/mes)     hotspots + cubos agregados
                                                                                │      ▲
                                                                   Redis (caché)│      │
                                                                                ▼      │
                                         apps/api (FastAPI) ◄──────────────────────────┘
                                         Martin/pg_tileserv (MVT)
                                                      │ JSON · CSV · MVT
                                                      ▼
                                         apps/web (React) → gestores de emergencias
```

| Componente                 | Tecnología                                        | Responsabilidad                                                      |
| -------------------------- | ------------------------------------------------- | -------------------------------------------------------------------- |
| Orquestación               | Prefect 3                                         | `backfill_flow` (histórico por año) y `nrt_daily_flow` (cron diario) |
| Procesamiento              | Python 3.12, polars/pandas, geopandas, h3, duckdb | Lógica de §6–§10                                                     |
| Almacenamiento de archivos | S3/MinIO + GeoParquet                             | Capas `raw`, `interim`, `harmonized`                                 |
| Base de datos              | PostgreSQL 16 + PostGIS 3                         | Tablas de §7.3, vistas materializadas                                |
| Caché                      | Redis                                             | Respuestas de `/calendar` y `/timeseries` por hash de consulta       |
| API                        | FastAPI                                           | Endpoints de §12                                                     |
| Teselas                    | Martin                                            | Capa `hotspots` en MVT                                               |
| Frontend                   | React + Vite + TS                                 | §13                                                                  |
| CI/CD                      | GitHub Actions + Turborepo                        | Lint, typecheck, tests, build, deploy                                |

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

El fin de misión de un satélite se registra en `packages/nina/sensor_lifecycle.yaml` y no cuenta como hueco.

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

- `packages/nina/known_gaps.yaml` con esos periodos (fechas exactas a confirmar con el
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

### 6.2 Reglas del validador (`packages/schemas/json/hotspot_input.schema.json`)

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

### 7.3 Tablas en PostGIS

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

### 9.3 Parámetros (en `packages/nina/src/nina/config.py`, sobreescribibles por variables de entorno)

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

Cada corrida escribe `source/reports/qa_<run_id>.json` con: filas leídas por archivo, filas aceptadas,
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
4. Guardar coeficientes en `source/harmonized/calibration_<version>.parquet`.

### 10.3 Validación (gate obligatorio)

- Validación cruzada dejando años fuera (_leave-one-year-out_) en 2012 → último año estándar.
- Métricas por estrato: sesgo relativo, R², RMSE, correlación de Spearman de la estacionalidad mensual.
- **Umbral de aceptación**: |sesgo relativo| ≤ 10 % y Spearman ≥ 0,8 en ≥ 80 % de los estratos con datos.
- Si no se cumple → el flujo falla, no publica y deja el reporte en `source/reports/validation_<version>.json`.
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
- Textos en `packages/schemas/legal/` (un solo lugar; la API y la web los importan de ahí).

---

## 12. API (`apps/api`)
r
> Detalle de endpoints, parámetros, errores y esquema `serving`: **`apps/api/API_CONTRACT.md`** (prevalece si difiere de esta sección).

Base: `/api/v1`. Todas las consultas reciben `region` (uno de: `region_id`, `bbox=minx,miny,maxx,maxy`
o `geometry` GeoJSON en POST) y `start`, `end` (`YYYY-MM-DD`, inclusivos).

| Método   | Ruta                                | Respuesta                                                                                                |
| -------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------- |
| GET      | `/regions?q=&level=`                | Regiones administrativas (id, nombre, nivel, bbox)                                                       |
| GET/POST | `/calendar`                         | Matriz año × mes: `count`, `climatology_median`, `anomaly_z`, `percentile`, `data_gap`, `is_provisional` |
| GET/POST | `/timeseries?freq=day\|week\|month` | Serie con banda climatológica (p10–p90)                                                                  |
| GET/POST | `/ranking`                          | Años ordenados por actividad en la región/periodo                                                        |
| GET/POST | `/hotspots?limit=&cursor=`          | Focos (GeoJSON) paginados                                                                                |
| GET/POST | `/export/hotspots.csv`              | CSV de focos de la consulta (streaming)                                                                  |
| GET/POST | `/export/calendar.csv`              | CSV de la matriz del calendario                                                                          |
| GET      | `/meta`                             | `harmonization_version`, cobertura, huecos, cita                                                         |

Límites: área máxima configurable (`MAX_AREA_KM2`), rango ≤ todo el dataset. Una consulta inválida devuelve
`422` con un mensaje para mostrar al usuario. Respuestas cacheadas en Redis 24 h, invalidadas al publicar
una nueva versión del dataset.

### 12.1 CSV de focos exportado

Separador `,`, UTF-8 con BOM (para Excel), fechas ISO-8601:

```
hotspot_id,acq_datetime_utc,acq_date_local,lat,lon,frp_mw,confidence_class,daynight,quality_level,is_provisional,harmonization_version
```

`instrument` y `satellite_norm` solo se incluyen si `?include_source=true`.

---

## 13. Frontend (`apps/web`)

- **Selección**: dibujar polígono/rectángulo (MapLibre + draw), buscar región administrativa o subir
  GeoJSON/Shapefile (zip). Selector de rango de fechas con atajos (este año, últimos 5 años, todo).
- **Calendario heatmap** (`packages/ui/CalendarHeatmap`): filas = años, columnas = meses.
    - Modo **conteo**: escala secuencial (log o cuantiles) — de claro a rojo oscuro.
    - Modo **anomalía**: escala divergente centrada en 0 (azul = menos que lo normal, rojo = más).
    - `data_gap` → celda gris con trama; `is_provisional` → borde punteado + tooltip "provisional".
    - Tooltip: conteo, mediana climatológica, anomalía, percentil.
    - Colores accesibles (daltonismo) y con leyenda siempre visible.
- **Serie temporal**: año seleccionado vs. banda climatológica y años previos. En la vista diaria, mostrar un aviso de
  sesgo de muestreo (`sampling_bias_warning`); los meses con `partial_coverage` se marcan como "cobertura incompleta".
- **Mapa**: puntos (MVT) y densidad por celda H3.
- **Descargas**: CSV de focos, CSV del calendario, PNG/SVG de gráficos.
- Pie con cita y advertencia (§11). i18n: `es` por defecto, `en` opcional.

---

## 14. Comandos

```bash
# Instalar
pnpm install
uv sync --all-packages

# Infra local (Postgres+PostGIS, Redis, MinIO, Martin)
docker compose --env-file .env -f infra/docker-compose.yml up -d

# Desarrollo
cp .env.example .env                      # y completar valores
pnpm turbo run dev --filter=@fire/web --filter=@fire/api

# Pipeline
uv run --package fire-pipelines python -m fire_pipelines.backfill --start 2000-11-01 --end 2011-12-31
uv run --package fire-pipelines python -m fire_pipelines.nrt_daily
uv run --package fire-pipelines python -m fire_pipelines.sp_replace
uv run --package fire-pipelines python -m fire_pipelines.validate --version <semver>

# Calidad
pnpm turbo run lint typecheck test --filter=...[origin/main]
pnpm turbo run test --filter=@fire/nina      # un solo paquete

# Dependencias
pnpm add <pkg> --filter @fire/web
uv add <pkg> --package nina

# Generar tipos TS desde OpenAPI
pnpm gen:types
```

---

## 15. Pruebas

- **Fixtures** mínimos en `packages/nina/tests/fixtures/`:
    - `modis_archive_sample.json` (incluye el objeto de ejemplo de §6),
    - `viirs_nrt_sample.json` (sin campo `type`),
    - `empty.json` (`[]`),
    - `mixed_invalid.json` (lat fuera de rango, `acq_time` `"618"`, `confidence` `"abc"`, satélite desconocido, Landsat).
- Tests obligatorios:
    - `acq_time "0000"` → `00:00 UTC`; `"618"` y `618` → `06:18 UTC`.
    - `confidence "48"` (MODIS) → `nominal`; `"29"` → `low`; `"h"` (VIIRS) → `high`.
    - Precedencia estándar > NRT para el mismo satélite y día.
    - NRT sin `type` no se rechaza por esquema.
    - Días de hueco conocidos → `data_gap = true`, nunca `count = 0`.
    - Archivo vacío → 0 filas, sin excepción.
    - La armonización conserva el orden de los años (correlación de rangos) en el solapamiento.
- API: tests de contrato contra OpenAPI; CSV exportado reabrible y con las columnas de §12.1.
- Web: tests de componente para `CalendarHeatmap` (escalas, gap, provisional) y un e2e (Playwright) del
  flujo región → fechas → calendario → descarga.

---

## 16. Convenciones

- Python: ruff + mypy estrictos, docstrings en español, funciones puras en `packages/nina` (I/O solo en
  `nina/io/`).
- TypeScript: `strict: true`, sin `any`, componentes funcionales, estado de servidor con TanStack Query.
- Commits: Conventional Commits (`feat(nina): ...`, `fix(api): ...`).
- Nombres de columnas y tablas en inglés `snake_case`; textos de UI en español.
- Logs estructurados (JSON) con `run_id` en el pipeline.

## 17. Definición de terminado

- [ ] Tests y linters en verde para todo lo afectado.
- [ ] Reporte de QA y de validación generados si se tocó el pipeline.
- [ ] ADR + versión nueva si cambió el método de armonización.
- [ ] Tipos TS regenerados si cambió la API.
- [ ] Cita y advertencia de FIRMS presentes en UI y exportaciones.
- [ ] `docs/` actualizado cuando cambia un comportamiento visible para el usuario.
