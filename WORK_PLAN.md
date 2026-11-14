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

| Rol | Persona | Agente | Responsabilidad |
|---|---|---|---|
| **A · Procesamiento y ciencia** | _(nombre)_ | Agente A | Ingesta FIRMS (Perú y mundial), adquisición remota, QA, esquema de la base, calibración/armonización y validación (N03–N11, N17) |
| **B · API y plataforma** | _(nombre)_ | Agente B | FastAPI, análisis y consultas, exportaciones, asistente, `openapi.json`, pruebas de API, entorno, Docker, CI, despliegue (N12, N15, N18) |
| **C · Web** | _(nombre)_ | Agente C | Interfaz React + CesiumJS: globo, selección, calendario, comparación, laboratorio, exportación, accesibilidad (N13, N14, N16) |

Si se suma una cuarta persona, conviene dividir **A**: A1 · ingesta y QA (`ingest.py`, `global_ingest.py`, `remote.py`) y
A2 · ciencia (`science.py`, notebooks, validación).

---

## 2. Propiedad de archivos (lo que cada agente puede escribir)

`nina/` es un solo paquete compartido por A y B, así que la propiedad es **por archivo**:

| Ruta | Dueño | Revisa | Notas |
|---|---|---|---|
| `nina/ingest.py`, `nina/global_ingest.py`, `nina/remote.py` | A | — | Toda la lógica específica de sensor |
| `nina/science.py` | A | B | Cambios de método → ADR (AGENTS §2.6) |
| `nina/store.py` | A | **B obligatorio** | **Frontera A→B**: esquema DuckDB |
| `scripts/` (salvo `export_openapi.py`) | A | — | Descarga, importación, verificación, inventario L2 |
| `data/boundaries/`, `docs/reference/`, `docs/DATA_SOURCES.md`, `docs/ACCEPTANCE_CRITERIA.md`, `notebooks/` | A | — | |
| `tests/test_global_ingest.py` | A | — | |
| `nina/main.py`, `nina/analytics.py`, `nina/assistant.py`, `nina/config.py` | B | A (solo `config.py`) | `main.py` + modelos de `analytics.py` = **frontera B→C** |
| `openapi.json`, `scripts/export_openapi.py` | B | **C obligatorio** | `openapi.json` se regenera, no se edita a mano |
| `tests/test_nina.py`, `tests/test_global_queries.py`, `pytest.ini` | B | — | A puede añadir pruebas de ingesta en `test_nina.py` con aviso |
| `requirements.txt`, `requirements.lock.txt`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `setup-nina.ps1`, `start-nina.ps1`, `.github/**`, `.env.example`, `.python-version` | B | A y C | Cambios pequeños y avisados |
| `web/**` | C | — | `web/src/types.ts` y `web/src/api.ts` siguen a `openapi.json` |
| `design/**`, `nina-demo.html`, `.nvmrc` | C | — | |
| `AGENTS.md`, `WORK_PLAN.md`, `README.md`, `docs/API_CONTRACT.md` | todos | todos (2 aprobaciones) | |
| `docs/adr/**`, `docs/ESTADO_*.md` | quien propone | todos | |
| `docs/requests/**` | cualquiera | rol destino | Solicitudes entre áreas (§7) |
| `source/`, `data/` (salvo `boundaries/`), `.env`, `.venv/`, `web/node_modules/`, `web/dist/` | nadie (local) | — | Gitignored |

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

| Frontera | Contrato | Doble para trabajar sin esperar | Quién lo provee |
|---|---|---|---|
| A → B | Tablas DuckDB de `nina/store.py` (`observations`, `batches`, `analyses`, …) y funciones públicas de `ingest`/`science` | Bases sintéticas creadas por `tests/` y el histórico público de Perú (`setup-nina.ps1 -DownloadData`, pocos minutos) | A |
| B → C | `openapi.json` (rutas `/api/*` y modelos) | El servidor local con el conjunto de Perú; para rutas nuevas, B publica primero la ruta con una respuesta de ejemplo fija | B |
| A → C (indirecta) | Estados `data_gap` / parcial / provisional en las respuestas | Casos en el conjunto peruano con huecos y meses parciales reales | A documenta, B los expone |

**Cómo se protege cada frontera (CI, bloquea el merge):**

- `pytest` cubre ingesta, consultas y exportaciones contra bases sintéticas.
- `npm run build` (con `tsc -b`) detecta tipos de la web desalineados.
- Pendiente para B (Fase 1): un paso de CI que regenere `openapi.json` y falle si difiere del commiteado.

---

## 4. Fases e hitos

Duración estimada: **1 a 2 semanas** por fase. ✅ = ya está en `main`.

### Fase 0 · Integración y base común → **Hito M0: "MVP en la raíz, contratos claros"**

| A · Procesamiento | B · API y plataforma | C · Web |
|---|---|---|
| ✅ Ingesta Perú + mundial 2025–2026, reconciliación SP/NRT | ✅ API `/api/*`, análisis, exportaciones, asistente | ✅ Globo, selección, calendario, comparación, laboratorio |
| ✅ `scripts/import_global.py` lee `source/` por defecto | ✅ CI: pytest + build web; `setup`/`start` desde la raíz | Revisar `web/src/types.ts` contra `openapi.json` |
| Documentar en `nina/store.py` el significado de cada columna y estado | `.github/CODEOWNERS`; paso de CI que verifica `openapi.json` | Inventario de pantallas y estados (carga, vacío, error, hueco) |

**M0 se cumple cuando:** los tres ejecutan `setup-nina.ps1` + `start-nina.ps1` desde la raíz, el CI está verde y
`CODEOWNERS` aplica la tabla de §2.

### Fase 1 · Datos y QA completos (N03–N06, N17)

| A | B | C |
|---|---|---|
| QA según AGENTS §9 (rangos, confianza unificada, tipo, duplicados) con motivos de rechazo contados | Endpoints de estado de calidad por lote (`batches`, rechazos) | Panel de procedencia y calidad del lote |
| Huecos y días sospechosos (`docs/reference/known_gaps.yaml`, §5.4) | Huecos y parciales en las respuestas del calendario | Hueco ≠ parcial ≠ cero en el calendario y la leyenda |
| Revisión NRT→SP idempotente | Validación y errores uniformes en todas las rutas | Accesibilidad de teclado en el globo y el calendario |

### Fase 2 · Ciencia de la armonización (N07–N11) → **Hito M1: "calibración evaluada"**

| A | B | C |
|---|---|---|
| Oportunidades de observación y emparejamientos (N07) | Rutas para modelos y su evaluación (sobre `science.py`) | Laboratorio: métricas, años y regiones reservados |
| Particiones, baseline y modelo candidato (N08–N09) | Exportación del manifiesto con versión del modelo | Comparación de años y ranking |
| Puentes Terra–Aqua y S-NPP↔NOAA-20 (N10) | | |
| Validación con los umbrales de AGENTS §10.3 + reporte en `data/reports/` | | |

**M1 se cumple cuando:** existe un reporte de validación reproducible y la decisión (aceptar o no) queda en un ADR.

### Fase 3 · Producto armonizado (N11–N15)

| A | B | C |
|---|---|---|
| Serie "equivalente VIIRS" versionada en DuckDB (AGENTS §10.4) | Métrica armonizada en análisis, calendario y exportaciones, con versión | Modo "armonizado" en el calendario, con aviso si el modelo no pasó la validación |
| | Asistente con referencias a la versión del modelo (N15) | Descargas con `LEEME`/cita (§11) |

### Fase 4 · Cierre (N16, N18) → **Hito M2: "release"**

| A | B | C |
|---|---|---|
| Reporte de aceptación (`docs/ACCEPTANCE_CRITERIA.md`) | Despliegue reproducible (Docker probado), *runbook* | Pruebas con usuarios (2 o 3 sesiones), ajustes de textos y color |
| Documentación de la metodología | Rendimiento de consultas con el archivo mundial | Demo guiada final |

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

| Tipo de cambio | Ejemplo | Proceso |
|---|---|---|
| **Aditivo** | Campo opcional nuevo, ruta nueva, columna nueva en DuckDB | PR `contract:` del dueño: código + `openapi.json` regenerado (o migración en `initialize()` de `store.py` con `ADD COLUMN IF NOT EXISTS`) + prueba. Aprueba el consumidor. |
| **Rompedor** | Renombrar o quitar un campo, cambiar un tipo o una semántica | RFC breve en `docs/contract-changes/NNNN-titulo.md`; lo aprueban los 3; luego PR `contract:`. El campo viejo se mantiene una fase. |
| **Interno** | Cambiar un cálculo sin cambiar la forma | PR normal. Si cambian los resultados científicos: ADR y nueva versión. |

Regla de oro: **ningún agente cambia un contrato en el mismo PR que la implementación que lo consume en otra área.**

---

## 7. Agentes: cómo trabaja cada uno

Cada persona ejecuta su agente desde la raíz del repo. El agente lee:

1. `AGENTS.md` (raíz).
2. El `AGENTS.md` de su área: A y B → `nina/AGENTS.md`; C → `web/AGENTS.md`.
3. Este plan y, si toca la API, `openapi.json`.

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

| Tema | Regla |
|---|---|
| Ramas | `nina/<slug>` (A), `api/<slug>` (B), `web/<slug>` (C), `contract/<slug>`, `infra/<slug>` |
| Rama principal | protegida: CI verde y aprobación de CODEOWNERS. *Squash merge* |
| Tamaño de PR | ≤ 400 líneas cambiadas (sin contar `openapi.json` ni lockfiles) |
| Sincronización | `git rebase origin/<principal>` al menos una vez al día |
| Commits | Conventional Commits: `feat(nina): …`, `fix(api): …`, `feat(web): …`, `contract: …`, `chore(infra): …`, `docs: …` |
| *Feature flags* | Funciones a medio terminar en la web, ocultas tras una constante o variable `VITE_FEATURE_*` |
| Reunión | 15 min dos veces por semana: hitos, bloqueos, `docs/requests/` |
| Demo | Al cerrar cada fase, una demo de punta a punta con datos reales |

---

## 9. Definición de terminado por rol

- **A:** pruebas de ingesta en verde, motivos de rechazo contados, criterios afectados de `docs/ACCEPTANCE_CRITERIA.md`
  marcados (`cumple` / `pendiente`), `docs/ESTADO_*.md` actualizado si cambian las cifras.
- **B:** la ruta está en `openapi.json` regenerado, tiene prueba, respeta hueco ≠ parcial ≠ cero y la web compila.
- **C:** la pantalla funciona contra el servidor local con datos reales, tiene estados de carga, vacío, error y hueco,
  y es usable con teclado.
