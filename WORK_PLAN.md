# Plan de trabajo · 3 personas, 3 agentes

> Ubicación en el repo: `WORK_PLAN.md` (raíz). Reglas globales: `AGENTS.md`. Contrato vigente de la API: `openapi.json`;
> contrato objetivo de la versión armonizada: `docs/API_CONTRACT.md`. Tareas científicas detalladas (N01–N18):
> `docs/PLAN_IMPLEMENTACION.md`.
>
> **Punto de partida:** el MVP NINA 0.3 ya funciona (globo, calendario, comparación, exportaciones, asistente, archivo
> mundial 2025–2026). Este plan reparte su evolución hacia la armonización validada entre tres personas, sin que se pisen.
>
> Tres principios:
>
> 1. **Contratos primero.** Las fronteras son el esquema DuckDB (`nina/store.py`) y la API (`openapi.json`).
> 2. **Cada persona es dueña de sus archivos.** Su agente solo escribe ahí.
> 3. **Cada frontera tiene un doble**, para que nadie dependa de que el otro haya terminado (§3).

---

## 1. Roles

| Rol                      | Persona    | Agente   | Paquetes (filtro turbo)                 | Responsabilidad                                                                                                           |
| ------------------------ | ---------- | -------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **A · Procesamiento**    | _(nombre)_ | Agente A | `@fire/nina`                            | Ingesta FIRMS, QA, armonización, validación, carga en `serving`, seed, `nina.stats`; más adelante `pipelines/` (jobs NRT) |
| **B · API y plataforma** | _(nombre)_ | Agente B | `@fire/api`, `@fire/schemas`            | FastAPI, modelos Pydantic → `openapi.json`, caché, exportaciones, teselas (Martin), Docker, CI/CD, despliegue             |
| **C · Web**              | _(nombre)_ | Agente C | `@fire/web`, `@fire/ui`, `@fire/config` | App React, `@fire/ui` (CalendarHeatmap, mapa, selectores), mocks de la API, accesibilidad, i18n                           |

Si se suma una cuarta persona, conviene dividir **A**: A1 · ingesta y QA (`ingest.py`, `global_ingest.py`, `remote.py`) y
A2 · ciencia (`science.py`, notebooks, validación).

---

## 2. Propiedad de archivos (lo que cada agente puede escribir)

`nina/` es un solo paquete compartido por A y B, así que la propiedad es **por archivo**:

| Ruta                                                                                       | Dueño            | Revisa                                     | Notas                                                                                                                     |
| ------------------------------------------------------------------------------------------ | ---------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `packages/nina/**`                                                                         | A                | B (solo `src/nina/stats.py` y `config.py`) | Incluye `known_gaps.yaml`, `sensor_lifecycle.yaml`, `ACCEPTANCE_CRITERIA.md`                                              |
| `pipelines/**` (desde la Fase 3)                                                           | A                | B                                          | Solo orquesta funciones de `nina`; se añade al workspace (`pnpm-workspace.yaml`, `pyproject.toml`) en un PR `infra:` de B |
| `notebooks/**`                                                                             | A                | —                                          | Nada aquí lo importa producción                                                                                           |
| `source/**`                                                                                | cada uno, local  | —                                          | Gitignored. Nunca se commitea                                                                                             |
| `packages/schemas/json/**`                                                                 | A                | B                                          | Contrato de entrada (AGENTS §6)                                                                                           |
| `packages/schemas/db/**` (DDL `serving`, migraciones, seed)                                | A                | **B obligatorio**                          | Frontera A→B                                                                                                              |
| `apps/api/**`                                                                              | B                | —                                          | `src/fire_api/models.py` es la frontera B→C: **C revisa obligatoriamente**                                                |
| `apps/api/API_CONTRACT.md`                                                                 | B                | **A y C obligatorio**                      | Documento de las dos fronteras                                                                                            |
| `packages/schemas/openapi/openapi.json`, `packages/schemas/src/generated/**`               | **nadie a mano** | C                                          | Se regeneran con `pnpm gen:types` en el mismo PR que cambia los modelos                                                   |
| `packages/schemas/legal/**`                                                                | B                | C                                          | Cita y avisos de FIRMS (un solo lugar; API y web los leen de aquí)                                                        |
| `packages/schemas/package.json`, `tsconfig.json`, `src/index.ts`                           | B                | C                                          |                                                                                                                           |
| `infra/**`, `.github/**`                                                                   | B                | —                                          |                                                                                                                           |
| Configuración raíz (`package.json`, `turbo.json`, `pnpm-workspace.yaml`, `pyproject.toml`) | B                | A y C                                      | Cambios pequeños y avisados                                                                                               |
| `.env.example`                                                                             | por sección      | B                                          | Cada rol añade variables **solo en su sección** (§2.1)                                                                    |
| `apps/web/**`                                                                              | C                | —                                          |                                                                                                                           |
| `packages/ui/**`                                                                           | C                | —                                          |                                                                                                                           |
| `packages/config/**` (TS/ESLint/Prettier)                                                  | C                | B                                          | ruff/mypy están en el `pyproject.toml` raíz (B)                                                                           |
| `uv.lock`, `pnpm-lock.yaml`                                                                | **nadie a mano** | —                                          | Si hay conflicto: tomar la versión de `main` y regenerar con `uv lock` / `pnpm install`                                   |
| `AGENTS.md` raíz, `WORK_PLAN.md`                                                           | todos            | todos (2 aprobaciones)                     |                                                                                                                           |
| `docs/adr/**`                                                                              | quien propone    | todos                                      |                                                                                                                           |
| `docs/requests/**`                                                                         | cualquiera       | rol destino                                | Solicitudes entre áreas (§7)                                                                                              |

Estas reglas se aplican con `.github/CODEOWNERS` (pendiente: B lo crea con los usuarios de GitHub) y con los
`AGENTS.md` de área: `nina/AGENTS.md` (A y B) y `web/AGENTS.md` (C).

### 2.1 Archivos compartidos sin conflictos

- **`nina/main.py`**: solo B. Si A necesita exponer algo nuevo, publica una función en su módulo y pide la ruta en
  `docs/requests/api-<slug>.md`.
- **`requirements.txt`**: una dependencia por línea, en orden alfabético; quien la añade regenera el lock en el mismo PR.
  En conflicto de lock: tomar el de `main` y regenerarlo, nunca resolverlo a mano.
- **`web/package-lock.json`**: igual (`npm.cmd --prefix web install`).
- **`.env.example`**: cada variable nueva con un comentario de una línea; la revisa B.

---

## 3. Fronteras y sus dobles

| Frontera | Contrato                                                                                                                                      | Doble para trabajar sin esperar                                                                                                                                                        | Quién lo provee                                                           | Cuándo           |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------------- |
| A → B    | `packages/schemas/db/serving.sql` + API_CONTRACT Parte B                                                                                      | **Seed sintético** `packages/schemas/db/seed/seed.sql.gz` (una región, 2001–2025, con huecos, provisionales y cobertura parcial), generado por `packages/schemas/db/seed/make_seed.py` | A                                                                         | Fin de la Fase 0 |
| A → B    | `nina.stats` (firmas, `packages/nina/src/nina/stats.py`)                                                                                      | Implementación inicial simple; las fórmulas finales llegan en la Fase 3                                                                                                                | A                                                                         | Fin de la Fase 0 |
| B → C    | Modelos Pydantic (`apps/api/src/fire_api/models.py`) → `packages/schemas/openapi/openapi.json` + tipos `@fire/schemas` + API_CONTRACT Parte A | **Mocks MSW** (`apps/web/src/mocks/`) hechos con los `examples` que B pone en los modelos                                                                                              | B escribe los modelos con `examples` y _stubs_ de rutas; C arma los mocks | Fin de la Fase 0 |
| B → C    | Teselas `serving.v_hotspots_tiles`                                                                                                            | GeoJSON estático con los focos del seed                                                                                                                                                | A (vista) + B (Martin)                                                    | Fase 2           |

**Cómo se protege cada frontera (CI, bloquea el merge):**

- **Fases 0–2 (sin tests):** `pnpm turbo run typecheck` es la red de seguridad. Como la web compila contra los tipos
  generados, un cambio en los modelos de B que rompa a C falla en el CI de ese mismo PR.
- **Desde la Fase 3 (tests de contrato, bloquean el merge):**
    - **A→B:** el loader de A valida que `serving` coincide con `serving.sql`. Los tests de la API corren contra el seed.
    - **B→C:** la API se prueba contra `openapi.json` con Schemathesis. El CI regenera `openapi.json` y falla si difiere del
      commiteado. La web compila con los tipos generados.

---

## 4. Fases e hitos

Duración estimada: **1 a 2 semanas** por fase. ✅ = ya está en `main`.

### Fase 0 · Integración y base común → **Hito M0: "MVP en la raíz, contratos claros"**

| A · Procesamiento                                                                  | B · API y plataforma                                                                             | C · Web                                                 |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| ✅ Esqueleto de `nina` + `config.py` + `known_gaps.yaml` + `sensor_lifecycle.yaml` | ✅ Esqueleto del monorepo (AGENTS §3.4), CI y docker-compose                                     | ✅ Esqueleto de Vite + React                            |
| ✅ `packages/schemas/json/hotspot_input.schema.json`                               | ✅ `/api/v1/meta` mínimo · ✅ `packages/schemas/legal/firms.json`                                | ✅ `@fire/config` (tsconfig, ESLint, Prettier)          |
| `serving.sql` v0.1 (con B)                                                         | `models.py` v0.1 + _stubs_ de todos los endpoints que devuelven sus `examples`; `pnpm gen:types` | Router + TanStack Query; mocks MSW desde los `examples` |
| Seed sintético + `make_seed.py`                                                    | `/health` con el seed cargado; `.github/CODEOWNERS`                                              | Wireframes: selección, calendario, serie, exportación   |
| Firmas de `stats.py`                                                               | Plantilla de _problem+json_ y de avisos                                                          | Estructura de `features/`                               |

**M0 se cumple cuando:** los tres ejecutan `setup-nina.ps1` + `start-nina.ps1` desde la raíz, el CI está verde y
`CODEOWNERS` aplica la tabla de §2.

### Fase 1 · Datos y QA completos (N03–N06, N17)

| A                                                                                     | B                                                   | C                                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------------- | --------------------------------------------------- |
| Ingesta FIRMS desde `source/`: lectores JSON/CSV/SHP, detección de origen (ING-01…06) | `/meta`, `/regions`, `/regions/{id}` sobre el seed  | Mapa (MapLibre) + `RegionPicker` (búsqueda, dibujo) |
| Normalización y esquema (SCH, TMP)                                                    | `POST /geometries` (GeoJSON/SHP, validación, Redis) | `DateRangePicker` acotado por `/meta`               |
| Confianza (CONF) + reporte de QA en `source/reports/` (OUT-01…03)                     | Middleware de errores, cabeceras, `ETag`            | i18n `es`                                           |
| Cliente de la API de FIRMS (SRC-04, SRC-07)                                           |                                                     | Pie con cita y aviso (desde `/meta`)                |

### Fase 2 · Ciencia de la armonización (N07–N11) → **Hito M1: "calibración evaluada"**

| A                                                                     | B                                                 | C                                                                                   |
| --------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Huecos (GAP-01…07) usando `known_gaps.yaml` y `sensor_lifecycle.yaml` | `/calendar` y `/timeseries` (usando `nina.stats`) | `CalendarHeatmap` en `@fire/ui`: modos conteo/anomalía, hueco, provisional, leyenda |
| Máscara de fuentes estáticas (TYPE)                                   | Caché en Redis, invalidación por versión          | Serie temporal con banda y aviso `SAMPLING_BIAS`                                    |
| Grilla H3 y `cell_day` (PIX)                                          | Vista de teselas + Martin                         | Capa de teselas en el mapa                                                          |

**M1 se cumple cuando:** existe un reporte de validación reproducible y la decisión (aceptar o no) queda en un ADR.

### Fase 3 · Producto armonizado (N11–N15)

| A                                                                     | B                                                                          | C                                                                     |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Calibración MODIS↔VIIRS (HAR-01…05)                                   | `/ranking`, `/hotspots` (cursor)                                           | Ranking de años, comparación de años                                  |
| Puente S-NPP↔NOAA-20 (SRC-02)                                         | `/export/hotspots` y `/export/calendar` (_streaming_, zip con `LEEME.txt`) | Botones de descarga, manejo de `EXPORT_TOO_LARGE`                     |
| Fórmulas finales de `stats` + validación dejando un año fuera         | Límites (`MAX_AREA_KM2`, `EXPORT_MAX_ROWS`)                                | Estados de error y vacíos para todos los códigos de API_CONTRACT §A.5 |
| Fixtures (AGENTS §15) y tests obligatorios de `nina`                  | Añade `test` a turbo/CI; Schemathesis y comparación de `openapi.json`      | Tests de componente de `CalendarHeatmap`                              |
| Crea `pipelines/` (`backfill`) y hace el backfill de la región piloto | PR `infra:` que añade `pipelines` al workspace                             |                                                                       |

### Fase 4 · Cierre (N16, N18) → **Hito M2: "release"**

| A                                                               | B                                                                 | C                                                             |
| --------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------- |
| Carga atómica en `serving` (B.2), `region_cell`, `region_month` | Tuning de consultas e índices contra los p95 de API_CONTRACT §A.6 | Rendimiento (muchas celdas, _lazy loading_)                   |
| Jobs `nrt_daily` y `sp_replace` programados                     | Despliegue en staging, observabilidad (logs, Sentry)              | Pruebas con usuarios: gestores de emergencia (2 o 3 sesiones) |
| Reporte de aceptación completo (ACCEPTANCE_CRITERIA)            | Tests de carga básicos                                            | Ajustes de escala de color y textos                           |

### Fase 5 · Endurecimiento → **Hito M3: "release v1.0"**

| A                                                             | B                                            | C                                                      |
| ------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------ |
| Validación externa (MCD64A1), documentación de la metodología | Despliegue en producción, backups, _runbook_ | Accesibilidad (WCAG AA), i18n `en`, e2e con Playwright |
| Todos los [OBL] cumplidos                                     | Contrato v1.0 congelado                      | Guía de usuario (`docs/user-guide.md`)                 |

---

## 5. Dependencias críticas

```
M0 ──► A: QA completo ──► A: ciencia (N07–N10) ──► M1 ──► A/B/C: producto armonizado ──► M2
 │                                                   ▲
 ├──► B: API sobre datos reales (Perú / mundial) ─────┤
 └──► C: UI sobre el servidor local ──────────────────┘
```

- **Camino crítico:** N07 (oportunidades de observación, máscaras L2). B y C no se bloquean: trabajan sobre las
  observaciones reales ya importadas.
- **Riesgo principal:** que la calibración no pase los umbrales. En ese caso el producto sigue mostrando observaciones por
  instrumento (como hoy) y la métrica armonizada queda como experimental. La API y la web no cambian de forma.

---

## 6. Cómo cambiar un contrato

| Tipo de cambio | Ejemplo                                                                           | Proceso                                                                                                                                                                                                                                                  |
| -------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Aditivo**    | Nuevo campo opcional en una respuesta, nuevo endpoint, nueva columna en `serving` | El dueño abre un PR con el prefijo `contract:`. Actualiza `models.py` (con `examples`) o el DDL, regenera con `pnpm gen:types`, actualiza el seed si aplica, `API_CONTRACT.md` y su historial. Sube la versión menor (0.1 → 0.2). Aprueba el consumidor. |
| **Rompedor**   | Renombrar o quitar un campo, cambiar un tipo o una semántica                      | Primero un RFC breve en `docs/contract-changes/NNNN-titulo.md` (motivo, impacto, migración). Lo aprueban los 3. Luego un PR `contract:` con versión mayor; en la API, el campo viejo se marca como _deprecated_ durante una fase.                        |
| **Interno**    | Cambiar cómo se calcula algo sin cambiar el contrato                              | PR normal del dueño. Si cambian los resultados de `stats` o de la armonización, se sube `HARMONIZATION_VERSION` y se escribe un ADR (AGENTS §2.5).                                                                                                       |

Regla de oro: **ningún agente cambia un contrato en el mismo PR que la implementación que lo consume en otra área.**

---

## 7. Agentes: cómo trabaja cada uno

Cada persona ejecuta su agente desde la raíz del repo. El agente lee:

1. `AGENTS.md` (raíz): reglas globales.
2. El `AGENTS.md` de su área (prevalece sobre la raíz para los archivos de esa carpeta):
    - A: `packages/nina/AGENTS.md`
    - B: `apps/api/AGENTS.md`
    - C: `apps/web/AGENTS.md` (cubre también `packages/ui` y `packages/config`)
3. `apps/api/API_CONTRACT.md` y este plan.

**Reglas comunes:**

- Solo escriben en los archivos de su rol (§2). Si necesitan algo de otra área, **no lo editan**: crean
  `docs/requests/<rol-destino>-<slug>.md` (qué, por qué, qué contrato toca) o un issue con la etiqueta `needs:<rol>`.
- Nunca editan a mano `openapi.json`, `requirements.lock.txt` ni `web/package-lock.json`.
- Nunca importan ni escriben sobre la base que usa un servidor en marcha (AGENTS §2.9).
- Antes de proponer un PR: `.\.venv\Scripts\python.exe -m pytest -q` y `npm.cmd --prefix web run build`.
- Si una prueba o la compilación falla por un cambio de otra área, **paran** y avisan a su persona.
- Cada PR enlaza la tarea del plan (p. ej., `Fase 2 · A · N09`) y los criterios de aceptación que cubre.

---

## 8. Git y ritmo de trabajo

| Tema            | Regla                                                                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Ramas           | `nina/<slug>`, `api/<slug>`, `web/<slug>`, `contract/<slug>`, `infra/<slug>`                                                                   |
| Rama principal  | `main` protegida: requiere CI verde y la aprobación de CODEOWNERS. _Squash merge_                                                              |
| Tamaño de PR    | ≤ 400 líneas cambiadas (sin contar archivos generados, lockfiles ni el seed)                                                                   |
| Sincronización  | `git rebase origin/main` al menos una vez al día                                                                                               |
| Commits         | Conventional Commits con alcance (AGENTS §16): `feat(nina): …`, `fix(api): …`, `feat(web): …`, `feat(ui): …`, `contract: …`, `chore(infra): …` |
| _Feature flags_ | Las funciones a medio terminar en la web se ocultan con `VITE_FEATURE_*` en lugar de esperar en una rama larga                                 |
| Reunión         | 15 min dos veces por semana: estado de los hitos, bloqueos, solicitudes en `docs/requests/`                                                    |
| Demo            | Al cerrar cada fase, una demo de punta a punta (aunque sea con el seed)                                                                        |

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

---

## 10. Tareas transversales de producto (Presi tasks)

Funciones que un MVP suele omitir pero que hacen que el producto se vea terminado. Cada una se reparte entre los tres
roles; se pueden empezar en paralelo a las fases (no dependen de la armonización).

### T1 · Usuarios y gestión de descargas

**Hoy:** no hay cuentas; cualquiera que abra la app puede importar, sincronizar y exportar.

- **Cuentas y roles:** inicio de sesión (correo + contraseña con hash, o login con Google/GitHub) y tres roles:
  `visitante` (solo consulta), `analista` (exporta, guarda análisis), `admin` (importa, sincroniza FIRMS, entrena modelos).
- **Rutas protegidas:** `/api/import`, `/api/sync`, `/api/acquisitions*`, `/api/models/train` solo para `admin`;
  exportaciones solo para usuarios autenticados.
- **Historial de descargas:** tabla `downloads` (usuario, análisis, tipo, filas, fecha, versión del dataset); pantalla
  "Mis descargas" para volver a bajar un archivo con los mismos filtros.
- **Análisis guardados y compartibles** por usuario (hoy ya existen enlaces; se asocian a su autor).
- **Cuotas y límites:** máximo de filas por exportación y de descargas por hora, con mensaje claro al superarlos.
- **Auditoría:** registro de quién importó, sincronizó o borró datos y cuándo.
- **Privacidad:** no guardar más datos personales de los necesarios; las claves FIRMS siguen solo en el servidor.

| A                                           | B                                                                    | C                                                             |
| ------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------- |
| Registrar el autor en importaciones y lotes | Autenticación, roles, tablas `users`/`downloads`/`audit_log`, cuotas | Login, registro, perfil, "Mis descargas", estados sin permiso |

**Terminado cuando:** un visitante no puede importar ni exportar, un analista ve su historial y un admin ve la auditoría.

### T2 · Validaciones de entrada (fechas, tipos, rangos)

**Hoy:** hay validaciones sueltas (años 2000–2100, mes 1–12, polígono WGS84, `days` 1–5), pero no hay reglas comunes ni mensajes uniformes.

- **Fechas:** `start ≤ end`; nada anterior al primer dato del sensor (p. ej. MODIS Terra 2000-11-01, S-NPP 2012-01-20)
  ni posterior al último día disponible; nada en el futuro; rango máximo configurable.
- **Coherencia de sensor:** producto y plataforma compatibles (Aqua solo con MODIS, NOAA-21 solo desde 2024, etc.).
- **Tipos y formatos:** fechas ISO `YYYY-MM-DD`, enumeraciones cerradas, longitudes máximas en textos, tamaño máximo de
  archivo subido, CSV con columnas FIRMS obligatorias y codificación UTF-8.
- **Geometría:** polígono válido, área máxima, dentro del ámbito elegido (ya existe en parte; se unifica).
- **Errores uniformes:** respuesta `422` con `code` y mensaje en español (tipo _problem+json_), mostrado tal cual en la UI.
- **Doble validación:** la UI valida antes de enviar (botón deshabilitado y mensaje junto al campo) y el servidor valida siempre.

| A                                                     | B                                                                                | C                                                                                         |
| ----------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Fechas de cobertura reales por sensor (desde la base) | Validadores comunes en los modelos Pydantic, códigos de error, pruebas por regla | Validación en formularios, selector de fechas acotado por la cobertura, mensajes de error |

**Terminado cuando:** cada regla tiene una prueba que envía un valor inválido y recibe su `code`, y la UI muestra el mensaje sin romperse.

### T3 · Filtrado por días (no solo por meses)

**Hoy:** la selección es por año y mes (`year_start`, `year_end`, `selected_year`, `selected_month`).

- **Rango libre de fechas:** `date_start` / `date_end` (inclusive, UTC) además del modo mensual; atajos como
  "últimos 7 días", "últimos 30 días", "esta temporada" o "este año".
- **Agregación configurable:** día, semana o mes. Por debajo de 8 días se muestra el aviso de **sesgo de muestreo** (AGENTS §8)
  y no se calculan anomalías.
- **Calendario diario:** vista de días dentro del mes seleccionado (heatmap tipo GitHub) que mantenga hueco ≠ cero.
- **Zona horaria:** opción de agrupar por fecha local (p. ej. `America/Lima`), con UTC por defecto.
- **Compatibilidad:** los enlaces y análisis guardados con el modo mensual siguen funcionando.
- **Rendimiento:** índice o partición por fecha en DuckDB para que los rangos cortos respondan rápido.

| A                                         | B                                                                                         | C                                                                         |
| ----------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Huecos y parciales también a nivel diario | Nuevos campos en la selección, agregación por día/semana, exportación con el rango exacto | Selector de rango con atajos, vista diaria del calendario, aviso de sesgo |

**Terminado cuando:** se elige un rango de 10 días, se ven los focos día a día y la exportación contiene exactamente esas fechas.

### Otras tareas de "producto terminado" (opcionales, suman en la presentación)

| Tarea                          | Qué aporta                                                                        | Rol   |
| ------------------------------ | --------------------------------------------------------------------------------- | ----- |
| Notificaciones / alertas       | Aviso (correo o en la app) cuando una región guardada supera su mediana histórica | B + C |
| Accesibilidad (WCAG AA)        | Teclado, contraste, lector de pantalla, paleta apta para daltonismo               | C     |
| Idioma inglés                  | Interfaz `es`/`en`                                                                | C     |
| Modo sin conexión / caché      | La app abre con los últimos datos aunque falle FIRMS                              | B     |
| Observabilidad                 | Logs estructurados, página de estado, métricas de uso y errores                   | B     |
| Página "Acerca de los datos"   | Metodología, limitaciones, versión del dataset, cita FIRMS                        | A + C |
| Copias de seguridad de la base | Respaldo y restauración de `nina.duckdb` documentados                             | B     |
| Onboarding                     | Recorrido guiado para usuarios nuevos (ya existe una versión; ampliarla)          | C     |
