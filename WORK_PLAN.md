# Plan de trabajo · 3 personas, 3 agentes

> Ubicación en el repo: `WORK_PLAN.md` (raíz). Contrato asociado: `apps/api/API_CONTRACT.md`.
> Objetivo: que Procesamiento (`nina`), API y Web avancen **en paralelo desde el primer día** sin pisarse.
> Se basa en tres principios:
>
> 1. **Contratos primero.** Antes de escribir lógica se fijan las fronteras: modelos de la API (→ `openapi.json`),
>    esquema `serving` y seed.
> 2. **Cada persona es dueña de sus carpetas.** Su agente solo escribe ahí.
> 3. **Cada frontera tiene un doble** (seed o mocks), para que nadie dependa de que el otro haya terminado.
>
> **Fase inicial (Fases 0–2): sin tests y sin `pipelines/`.** La verificación es `pnpm turbo run lint typecheck`.
> Los tests y `pipelines/` se introducen en la Fase 3 (§4). Todos los datos FIRMS (crudos y derivados) viven en
> `source/` (gitignored); cada persona mantiene su copia local.

---

## 1. Roles

| Rol | Persona | Agente | Paquetes (filtro turbo) | Responsabilidad |
|---|---|---|---|---|
| **A · Procesamiento** | _(nombre)_ | Agente A | `@fire/nina` | Ingesta FIRMS, QA, armonización, validación, carga en `serving`, seed, `nina.stats`; más adelante `pipelines/` (jobs NRT) |
| **B · API y plataforma** | _(nombre)_ | Agente B | `@fire/api`, `@fire/schemas` | FastAPI, modelos Pydantic → `openapi.json`, caché, exportaciones, teselas (Martin), Docker, CI/CD, despliegue |
| **C · Web** | _(nombre)_ | Agente C | `@fire/web`, `@fire/ui`, `@fire/config` | App React, `@fire/ui` (CalendarHeatmap, mapa, selectores), mocks de la API, accesibilidad, i18n |

**¿Hace falta una cuarta persona?** No es obligatorio: la plataforma (Docker, CI y despliegue) cabe en B. Si se suma alguien,
conviene dividir **A**, que es el rol con más carga y más riesgo técnico:

- **A1 · Ingesta y QA:** ING, SCH, TMP, CONF, GAP, TYPE (`nina/io/`, `nina/qa/`, `ingest.py`, `normalize.py`).
- **A2 · Armonización y validación:** HAR, SRC-02, `stats`, notebooks (`grid.py`, `calibration.py`, `bridge.py`, `validation.py`, `stats.py`).

---

## 2. Propiedad de carpetas (lo que cada agente puede escribir)

| Ruta | Dueño | Revisa | Notas |
|---|---|---|---|
| `packages/nina/**` | A | B (solo `src/nina/stats.py` y `config.py`) | Incluye `known_gaps.yaml`, `sensor_lifecycle.yaml`, `ACCEPTANCE_CRITERIA.md` |
| `pipelines/**` (desde la Fase 3) | A | B | Solo orquesta funciones de `nina`; se añade al workspace (`pnpm-workspace.yaml`, `pyproject.toml`) en un PR `infra:` de B |
| `notebooks/**` | A | — | Nada aquí lo importa producción |
| `source/**` | cada uno, local | — | Gitignored. Nunca se commitea |
| `packages/schemas/json/**` | A | B | Contrato de entrada (AGENTS §6) |
| `packages/schemas/db/**` (DDL `serving`, migraciones, seed) | A | **B obligatorio** | Frontera A→B |
| `apps/api/**` | B | — | `src/fire_api/models.py` es la frontera B→C: **C revisa obligatoriamente** |
| `apps/api/API_CONTRACT.md` | B | **A y C obligatorio** | Documento de las dos fronteras |
| `packages/schemas/openapi/openapi.json`, `packages/schemas/src/generated/**` | **nadie a mano** | C | Se regeneran con `pnpm gen:types` en el mismo PR que cambia los modelos |
| `packages/schemas/legal/**` | B | C | Cita y avisos de FIRMS (un solo lugar; API y web los leen de aquí) |
| `packages/schemas/package.json`, `tsconfig.json`, `src/index.ts` | B | C | |
| `infra/**`, `.github/**` | B | — | |
| Configuración raíz (`package.json`, `turbo.json`, `pnpm-workspace.yaml`, `pyproject.toml`) | B | A y C | Cambios pequeños y avisados |
| `.env.example` | por sección | B | Cada rol añade variables **solo en su sección** (§2.1) |
| `apps/web/**` | C | — | |
| `packages/ui/**` | C | — | |
| `packages/config/**` (TS/ESLint/Prettier) | C | B | ruff/mypy están en el `pyproject.toml` raíz (B) |
| `uv.lock`, `pnpm-lock.yaml` | **nadie a mano** | — | Si hay conflicto: tomar la versión de `main` y regenerar con `uv lock` / `pnpm install` |
| `AGENTS.md` raíz, `WORK_PLAN.md` | todos | todos (2 aprobaciones) | |
| `docs/adr/**` | quien propone | todos | |
| `docs/requests/**` | cualquiera | rol destino | Solicitudes entre áreas (§7) |

Estas reglas se aplican con `.github/CODEOWNERS` (pendiente: B lo crea en la Fase 0 con los usuarios de GitHub) y con el
`AGENTS.md` de cada área (§7).

### 2.1 Archivos compartidos sin conflictos

Los archivos que todos tocan se dividen para que dos PR no editen las mismas líneas:

- **`.env.example`**: tres secciones con encabezado (`# --- A · nina ---`, `# --- B · API/infra ---`, `# --- C · web ---`).
  Se añade al final de la sección propia.
- **Dependencias**: cada uno solo en su paquete (`uv add <pkg> --package nina`, `pnpm add <pkg> --filter @fire/web`).
  Nunca en la raíz salvo herramientas comunes (PR de B).
- **Routers de la API**: un archivo por endpoint en `apps/api/src/fire_api/routers/`; `main.py` solo los monta.
- **Features de la web**: una carpeta por feature en `apps/web/src/features/`; las rutas viven en `apps/web/src/app/`.

---

## 3. Fronteras y sus dobles

| Frontera | Contrato | Doble para trabajar sin esperar | Quién lo provee | Cuándo |
|---|---|---|---|---|
| A → B | `packages/schemas/db/serving.sql` + API_CONTRACT Parte B | **Seed sintético** `packages/schemas/db/seed/seed.sql.gz` (una región, 2001–2025, con huecos, provisionales y cobertura parcial), generado por `packages/schemas/db/seed/make_seed.py` | A | Fin de la Fase 0 |
| A → B | `nina.stats` (firmas, `packages/nina/src/nina/stats.py`) | Implementación inicial simple; las fórmulas finales llegan en la Fase 3 | A | Fin de la Fase 0 |
| B → C | Modelos Pydantic (`apps/api/src/fire_api/models.py`) → `packages/schemas/openapi/openapi.json` + tipos `@fire/schemas` + API_CONTRACT Parte A | **Mocks MSW** (`apps/web/src/mocks/`) hechos con los `examples` que B pone en los modelos | B escribe los modelos con `examples` y *stubs* de rutas; C arma los mocks | Fin de la Fase 0 |
| B → C | Teselas `serving.v_hotspots_tiles` | GeoJSON estático con los focos del seed | A (vista) + B (Martin) | Fase 2 |

**Cómo se protege cada frontera:**

- **Fases 0–2 (sin tests):** `pnpm turbo run typecheck` es la red de seguridad. Como la web compila contra los tipos
  generados, un cambio en los modelos de B que rompa a C falla en el CI de ese mismo PR.
- **Desde la Fase 3 (tests de contrato, bloquean el merge):**
  - **A→B:** el loader de A valida que `serving` coincide con `serving.sql`. Los tests de la API corren contra el seed.
  - **B→C:** la API se prueba contra `openapi.json` con Schemathesis. El CI regenera `openapi.json` y falla si difiere del
    commiteado. La web compila con los tipos generados.

---

## 4. Fases e hitos

Las fases tienen una duración estimada de **1 a 2 semanas** cada una. Ajústala al calendario real; lo importante es el orden y
los hitos. ✅ = ya está en `main`.

### Fase 0 · Contratos y esqueleto → **Hito M0: "contratos congelados v0.1"**

| A · Procesamiento | B · API y plataforma | C · Web |
|---|---|---|
| ✅ Esqueleto de `nina` + `config.py` + `known_gaps.yaml` + `sensor_lifecycle.yaml` | ✅ Esqueleto del monorepo (AGENTS §3.4), CI y docker-compose | ✅ Esqueleto de Vite + React |
| ✅ `packages/schemas/json/hotspot_input.schema.json` | ✅ `/api/v1/meta` mínimo · ✅ `packages/schemas/legal/firms.json` | ✅ `@fire/config` (tsconfig, ESLint, Prettier) |
| `serving.sql` v0.1 (con B) | `models.py` v0.1 + *stubs* de todos los endpoints que devuelven sus `examples`; `pnpm gen:types` | Router + TanStack Query; mocks MSW desde los `examples` |
| Seed sintético + `make_seed.py` | `/health` con el seed cargado; `.github/CODEOWNERS` | Wireframes: selección, calendario, serie, exportación |
| Firmas de `stats.py` | Plantilla de *problem+json* y de avisos | Estructura de `features/` |

**M0 se cumple cuando:** `serving.sql`, el seed, `models.py` y el `openapi.json` generado están en `main`, el CI
(lint + typecheck) está verde y los tres pueden ejecutar `docker compose --env-file .env -f infra/docker-compose.yml up -d` + seed.

### Fase 1 · Funcionalidad básica en paralelo

| A | B | C |
|---|---|---|
| Ingesta FIRMS desde `source/`: lectores JSON/CSV/SHP, detección de origen (ING-01…06) | `/meta`, `/regions`, `/regions/{id}` sobre el seed | Mapa (MapLibre) + `RegionPicker` (búsqueda, dibujo) |
| Normalización y esquema (SCH, TMP) | `POST /geometries` (GeoJSON/SHP, validación, Redis) | `DateRangePicker` acotado por `/meta` |
| Confianza (CONF) + reporte de QA en `source/reports/` (OUT-01…03) | Middleware de errores, cabeceras, `ETag` | i18n `es` |
| Cliente de la API de FIRMS (SRC-04, SRC-07) | | Pie con cita y aviso (desde `/meta`) |

### Fase 2 · Calendario de punta a punta con el seed → **Hito M1: "flujo completo con el seed"**

| A | B | C |
|---|---|---|
| Huecos (GAP-01…07) usando `known_gaps.yaml` y `sensor_lifecycle.yaml` | `/calendar` y `/timeseries` (usando `nina.stats`) | `CalendarHeatmap` en `@fire/ui`: modos conteo/anomalía, hueco, provisional, leyenda |
| Máscara de fuentes estáticas (TYPE) | Caché en Redis, invalidación por versión | Serie temporal con banda y aviso `SAMPLING_BIAS` |
| Grilla H3 y `cell_day` (PIX) | Vista de teselas + Martin | Capa de teselas en el mapa |

**M1 se cumple cuando:** en la web real (sin mocks) se elige una región del seed y un rango de fechas, y se ve el calendario con huecos y meses provisionales correctos.

### Fase 3 · Armonización real, tests y `pipelines/`

| A | B | C |
|---|---|---|
| Calibración MODIS↔VIIRS (HAR-01…05) | `/ranking`, `/hotspots` (cursor) | Ranking de años, comparación de años |
| Puente S-NPP↔NOAA-20 (SRC-02) | `/export/hotspots` y `/export/calendar` (*streaming*, zip con `LEEME.txt`) | Botones de descarga, manejo de `EXPORT_TOO_LARGE` |
| Fórmulas finales de `stats` + validación dejando un año fuera | Límites (`MAX_AREA_KM2`, `EXPORT_MAX_ROWS`) | Estados de error y vacíos para todos los códigos de API_CONTRACT §A.5 |
| Fixtures (AGENTS §15) y tests obligatorios de `nina` | Añade `test` a turbo/CI; Schemathesis y comparación de `openapi.json` | Tests de componente de `CalendarHeatmap` |
| Crea `pipelines/` (`backfill`) y hace el backfill de la región piloto | PR `infra:` que añade `pipelines` al workspace | |

### Fase 4 · Integración con datos reales → **Hito M2: "dataset real v0.x en staging"**

| A | B | C |
|---|---|---|
| Carga atómica en `serving` (B.2), `region_cell`, `region_month` | Tuning de consultas e índices contra los p95 de API_CONTRACT §A.6 | Rendimiento (muchas celdas, *lazy loading*) |
| Jobs `nrt_daily` y `sp_replace` programados | Despliegue en staging, observabilidad (logs, Sentry) | Pruebas con usuarios: gestores de emergencia (2 o 3 sesiones) |
| Reporte de aceptación completo (ACCEPTANCE_CRITERIA) | Tests de carga básicos | Ajustes de escala de color y textos |

### Fase 5 · Endurecimiento → **Hito M3: "release v1.0"**

| A | B | C |
|---|---|---|
| Validación externa (MCD64A1), documentación de la metodología | Despliegue en producción, backups, *runbook* | Accesibilidad (WCAG AA), i18n `en`, e2e con Playwright |
| Todos los [OBL] cumplidos | Contrato v1.0 congelado | Guía de usuario (`docs/user-guide.md`) |

---

## 5. Dependencias críticas

```
M0 ──► A: ingesta/QA ─────────► A: armonización ──► A: carga real ──► M2 ──► M3
 │                                                     ▲
 ├──► B: endpoints sobre seed ──► M1 ──► B: export ────┤
 │                                ▲                    │
 └──► C: UI sobre mocks ──────────┘──► C: UI completa ─┘
```

- **Camino crítico:** la armonización de A (Fase 3) y la carga real (Fase 4). B y C no se bloquean gracias al seed y a los mocks.
- **Riesgo principal:** que la validación de la armonización no pase los umbrales (HAR-03). En ese caso se publica el
  dataset en staging con `harmonization_version` `0.x` y un aviso en la UI. La web y la API no cambian.

---

## 6. Cómo cambiar un contrato

| Tipo de cambio | Ejemplo | Proceso |
|---|---|---|
| **Aditivo** | Nuevo campo opcional en una respuesta, nuevo endpoint, nueva columna en `serving` | El dueño abre un PR con el prefijo `contract:`. Actualiza `models.py` (con `examples`) o el DDL, regenera con `pnpm gen:types`, actualiza el seed si aplica, `API_CONTRACT.md` y su historial. Sube la versión menor (0.1 → 0.2). Aprueba el consumidor. |
| **Rompedor** | Renombrar o quitar un campo, cambiar un tipo o una semántica | Primero un RFC breve en `docs/contract-changes/NNNN-titulo.md` (motivo, impacto, migración). Lo aprueban los 3. Luego un PR `contract:` con versión mayor; en la API, el campo viejo se marca como *deprecated* durante una fase. |
| **Interno** | Cambiar cómo se calcula algo sin cambiar el contrato | PR normal del dueño. Si cambian los resultados de `stats` o de la armonización, se sube `HARMONIZATION_VERSION` y se escribe un ADR (AGENTS §2.5). |

Regla de oro: **ningún agente cambia un contrato en el mismo PR que la implementación que lo consume.** Primero se fusiona el PR
`contract:` (que sí incluye los archivos regenerados, AGENTS §2.6), y después cada uno implementa en su área.

---

## 7. Agentes: cómo trabaja cada uno

Cada persona ejecuta su agente desde la raíz del repo. El agente lee:

1. `AGENTS.md` (raíz): reglas globales.
2. El `AGENTS.md` de su área (prevalece sobre la raíz para los archivos de esa carpeta):
   - A: `packages/nina/AGENTS.md`
   - B: `apps/api/AGENTS.md`
   - C: `apps/web/AGENTS.md` (cubre también `packages/ui` y `packages/config`)
3. `apps/api/API_CONTRACT.md` y este plan.

**Reglas comunes a los tres agentes:**

- Solo escriben en las rutas de su rol (§2). Si necesitan algo de otra área, **no lo editan**: crean
  `docs/requests/<rol-destino>-<slug>.md` (qué se necesita, por qué, qué contrato toca) o un issue con la etiqueta `needs:<rol>`.
- Nunca editan a mano `packages/schemas/openapi/**`, `packages/schemas/src/generated/**`, `uv.lock` ni `pnpm-lock.yaml`.
- Nunca leen ni escriben `source/` fuera del rol A (B y C trabajan con el seed y los mocks).
- Antes de proponer un PR ejecutan, para su área: `pnpm turbo run lint typecheck --filter=...[origin/main]`
  (desde la Fase 3 se añade `test`).
- Si el typecheck (o, más adelante, un test de contrato) falla por un cambio de otra área, **paran** y avisan a su persona;
  no "arreglan" el contrato, el DDL ni los tipos generados para que pase.
- Cada PR enlaza la tarea del plan (p. ej., `Fase 2 · B · /calendar`) y los criterios de aceptación que cubre.

---

## 8. Git y ritmo de trabajo

| Tema | Regla |
|---|---|
| Ramas | `nina/<slug>`, `api/<slug>`, `web/<slug>`, `contract/<slug>`, `infra/<slug>` |
| Rama principal | `main` protegida: requiere CI verde y la aprobación de CODEOWNERS. *Squash merge* |
| Tamaño de PR | ≤ 400 líneas cambiadas (sin contar archivos generados, lockfiles ni el seed) |
| Sincronización | `git rebase origin/main` al menos una vez al día |
| Commits | Conventional Commits con alcance (AGENTS §16): `feat(nina): …`, `fix(api): …`, `feat(web): …`, `feat(ui): …`, `contract: …`, `chore(infra): …` |
| *Feature flags* | Las funciones a medio terminar en la web se ocultan con `VITE_FEATURE_*` en lugar de esperar en una rama larga |
| Reunión | 15 min dos veces por semana: estado de los hitos, bloqueos, solicitudes en `docs/requests/` |
| Demo | Al cerrar cada fase, una demo de punta a punta (aunque sea con el seed) |

---

## 9. Definición de terminado por rol

**Fases 0–2:**

- **A:** lint y typecheck de `@fire/nina` en verde; criterios [OBL] del área revisados; seed actualizado si cambió `serving`.
- **B:** el endpoint coincide con API_CONTRACT, `openapi.json` y los tipos están regenerados, funciona contra el seed y la web compila.
- **C:** la feature funciona contra los mocks **y** contra la API real con el seed, y tiene estados de carga, vacío y error.

**Desde la Fase 3** se suma a lo anterior:

- **A:** reporte de aceptación generado en `source/reports/` y tests obligatorios de AGENTS §15 en verde.
- **B:** Schemathesis en verde, tests sobre el seed y p95 cumplido en staging.
- **C:** test de componente y axe sin errores críticos.
