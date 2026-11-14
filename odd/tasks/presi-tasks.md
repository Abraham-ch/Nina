# presi-tasks · Tareas transversales de producto (WORK_PLAN.md §10)

- **Objetivo:** implementar T1, T2 y T3 de `WORK_PLAN.md` §10 sobre la rama `mvp-abraham`.
- **Rama:** `anthony/tasks` (base `origin/mvp-abraham` @ `90d2ed6`) → PRs hacia `mvp-abraham`, una tarea por PR.
- **Estrategia de entrega:** `ask-on-risk`; unidades de trabajo de ~400 líneas autorizadas (WORK_PLAN §8). Si una tarea supera
  ese presupuesto se parte en varios PRs, cada uno enlazando la tarea del plan.
- **Verificación:** `python -m pytest -q` ( `.venv/bin/python -m pytest -q` si existe el venv ) y `npm --prefix web run build`.
- **Ruta:** inline en todos los casos — ninguna condición de delegación dispara.

---

## Specs

> Texto citado **verbatim** de `WORK_PLAN.md` §10, rama `mvp-abraham`. No se resume ni se rewordtea.

### S1 · T1 · Usuarios y gestión de descargas

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

| A | B | C |
|---|---|---|
| Registrar el autor en importaciones y lotes | Autenticación, roles, tablas `users`/`downloads`/`audit_log`, cuotas | Login, registro, perfil, "Mis descargas", estados sin permiso |

**Terminado cuando:** un visitante no puede importar ni exportar, un analista ve su historial y un admin ve la auditoría.

### S2 · T2 · Validaciones de entrada (fechas, tipos, rangos)

**Hoy:** hay validaciones sueltas (años 2000–2100, mes 1–12, polígono WGS84, `days` 1–5), pero no hay reglas comunes ni mensajes uniformes.

- **Fechas:** `start ≤ end`; nada anterior al primer dato del sensor (p. ej. MODIS Terra 2000-11-01, S-NPP 2012-01-20)
  ni posterior al último día disponible; nada en el futuro; rango máximo configurable.
- **Coherencia de sensor:** producto y plataforma compatibles (Aqua solo con MODIS, NOAA-21 solo desde 2024, etc.).
- **Tipos y formatos:** fechas ISO `YYYY-MM-DD`, enumeraciones cerradas, longitudes máximas en textos, tamaño máximo de
  archivo subido, CSV con columnas FIRMS obligatorias y codificación UTF-8.
- **Geometría:** polígono válido, área máxima, dentro del ámbito elegido (ya existe en parte; se unifica).
- **Errores uniformes:** respuesta `422` con `code` y mensaje en español (tipo _problem+json_), mostrado tal cual en la UI.
- **Doble validación:** la UI valida antes de enviar (botón deshabilitado y mensaje junto al campo) y el servidor valida siempre.

| A | B | C |
|---|---|---|
| Fechas de cobertura reales por sensor (desde la base) | Validadores comunes en los modelos Pydantic, códigos de error, pruebas por regla | Validación en formularios, selector de fechas acotado por la cobertura, mensajes de error |

**Terminado cuando:** cada regla tiene una prueba que envía un valor inválido y recibe su `code`, y la UI muestra el mensaje sin romperse.

### S3 · T3 · Filtrado por días (no solo por meses)

**Hoy:** la selección es por año y mes (`year_start`, `year_end`, `selected_year`, `selected_month`).

- **Rango libre de fechas:** `date_start` / `date_end` (inclusive, UTC) además del modo mensual; atajos como
  "últimos 7 días", "últimos 30 días", "esta temporada" o "este año".
- **Agregación configurable:** día, semana o mes. Por debajo de 8 días se muestra el aviso de **sesgo de muestreo** (AGENTS §8)
  y no se calculan anomalías.
- **Calendario diario:** vista de días dentro del mes seleccionado (heatmap tipo GitHub) que mantenga hueco ≠ cero.
- **Zona horaria:** opción de agrupar por fecha local (p. ej. `America/Lima`), con UTC por defecto.
- **Compatibilidad:** los enlaces y análisis guardados con el modo mensual siguen funcionando.
- **Rendimiento:** índice o partición por fecha en DuckDB para que los rangos cortos respondan rápido.

| A | B | C |
|---|---|---|
| Huecos y parciales también a nivel diario | Nuevos campos en la selección, agregación por día/semana, exportación con el rango exacto | Selector de rango con atajos, vista diaria del calendario, aviso de sesgo |

**Terminado cuando:** se elige un rango de 10 días, se ven los focos día a día y la exportación contiene exactamente esas fechas.

### S4 · Supuestos

- **A1 (asunción, confirmar antes de cerrar T1):** "todas" = las tres tareas **completas**, es decir las columnas
  **A + B + C** de cada una. Si el alcance es solo la columna de un rol, reescribir S1–S3 acotándolas y reabrir las tareas.
- **A2 (asunción):** se trabaja sobre el layout real de `mvp-abraham` (`nina/`, `web/`, `scripts/`, `tests/`), que es el
  que gobierna `AGENTS.md` raíz + `nina/AGENTS.md`. Las rutas `packages/**` y `apps/**` del `WORK_PLAN.md` §2 **no existen**
  en esta rama y no se crean.

---

## Tasks

| ID | Spec | Ruta | Estado | Commit |
|---|---|---|---|---|
| T1 | S1 (+ A1, A2) | inline | pendiente | — |
| T2 | S2 (+ A1, A2) | inline | pendiente | — |
| T3 | S3 (+ A1, A2) | inline | pendiente | — |

---

## Log

- **L1** · petición original del usuario, verbatim:
  > hay que hacer todas, encima de la rama de mvp-abraham
- **L2** · instrucción de entrega, verbatim:
  > sacame una rama entonces como anthony/tasks y arrancamos. Vamos haciendo prs a mvp-abraham task x task
- **L3** · la sección señalada por el lead, verbatim:
  > tareas transversales de producto se llama la sección
- **L4** · rama creada `anthony/tasks` desde `origin/mvp-abraham` @ `90d2ed6`. Verificado que `.gitignore` cubre
  `/source/*` y `*.zip`: los ZIPs de FIRMS en `source/` no se trackean.
- **L5** · contexto de arranque verificado contra el código: `/api/import`, `/api/sync`, `/api/acquisitions*` y
  `/api/models/train` existen en `nina/main.py` y están **sin proteger**; `nina/store.py` crea `observations`,
  `batches`, `analyses`, `jobs` — **no** existen `users`, `downloads` ni `audit_log`. El "Hoy" de §10 es exacto.
