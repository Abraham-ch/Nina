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
- **Errores uniformes:** a `422` response with a `code` and a message (_problem+json_ style), shown as is in the UI, **in the interface language**.
  > Texto vigente de `WORK_PLAN.md` §10. Sustituye al original en español —"respuesta `422` con `code` y
  > mensaje en español"—, que era el que regía al empezar T2. **Cambio de requisito registrado en L38**;
  > el resto de `S2` es semánticamente idéntico en las dos versiones (ver L32).
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
| T1 | S1 (+ A1, A2) | inline | **S1 completa**: `MAX_EXPORT_ROWS` implementado y los advisories de seguridad cerrados; solo quedan menores (`rows=0` en `manifest`/`report`, detalle del servidor sin traducir, clase muerta) | `c6721fc`, `d879306`, `003a86a`, `c78fb0f`, `5bf79b7`, `0245a72` |
| T2 | S2 (+ A1, A2) | inline | **celda A hecha** (cobertura real desde la base, `date_future`/`date_range` en import, `FIRMS_MAX_DAY_RANGE` configurable); **falta la celda C** (UI) y el CSV con columnas FIRMS/UTF-8 | `2127ee7`, `ae69bc8` |
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
- **L6** · **RED observado** antes de implementar: `tests/test_auth.py` → `12 failed` (rutas que devuelven 404 y
  columnas inexistentes). No se escribió código de producción antes de verlo fallar.
- **L7** · **GREEN observado**: `python -m pytest -q` → **`45 passed`** (33 preexistentes + 12 nuevos).
  `npm --prefix web run build` → `✓ built in 4.24s`. Entorno: venv con Python 3.14 (`.python-version`) y
  `requirements.lock.txt` intacto — **sin dependencias nuevas** (PBKDF2 viene de `hashlib`).
- **L8** · **Regresión detectada por la comprobación diferencial y corregida**: `nina/ingest.py` y
  `nina/analytics.py` hacían `INSERT … VALUES (?)` **posicional**; al añadir `created_by` a `batches`/`analyses`
  ambos rompían con `_duckdb.BinderException: table "batches" has 17 columns but 16 values were supplied`.
  Pasa a lista de columnas explícita en los dos sitios.
- **L9** · **Cambio de comportamiento deliberado en `tests/test_nina.py`**: el fixture `client` ahora registra una
  cuenta `admin` al abrirse. Es consecuencia directa de S1 ("exportaciones solo para usuarios autenticados",
  rutas de administración solo para `admin`), no una adaptación silenciosa: los tests de datos se ejecutan como
  operador autenticado. Los tests de autorización viven aparte en `tests/test_auth.py` con fixture propio anónimo.
- **L10** · Commits de la tarea: `fb8ff88` (documento de feature) y `a0438d5` (backend de T1, **395 líneas
  autorizadas** = 557 − 172 de `openapi.json` generado, dentro del presupuesto de 400 de WORK_PLAN §8).
- **L11** · `openapi.json` regenerado con `scripts/export_openapi.py`: +4 rutas (`/api/auth/register`,
  `/login`, `/logout`, `/me`). `web/src/types.ts` y `web/src/api.ts` se actualizan en el PR de T1 junto con la
  interfaz (regla 7: mismo PR, no mismo commit).
- **L12** · **Verificación independiente** (`gentle-ai-verify`) sobre `a0438d5` → **`advisories`, cero blockers**.
  53/53 probes de S1 en verde; suite `45 passed` (base `33 passed`); diferencial base↔candidato idéntico salvo
  la columna añadida `created_by`; esquema **aditivo sin problemas** (`PROBLEMS: none`); `openapi.json`
  byte-idéntico al regenerar; build web `✓ built in 4.26s`. Spot check del padre: `45 passed` ✅.
  **Aún no implementado** (coincide con el estado "en curso" de T1): historial `downloads` + pantalla
  "Mis descargas", relleno de `created_by` (T1-A), cuotas, escritura y vista de `audit_log`.
- **L13** · **Advisories del verificador → van en el siguiente corte de T1** (no se tocan los bytes ya
  verificados): (1) cookie sin `secure` → condicionarlo al esquema de la petición; (2) PBKDF2 200 000 rondas
  vs. 600 000 de OWASP — el hash guarda las rondas, se sube sin romper contraseñas existentes; (3) registro
  abierto a `analista` sin aprobación; (4) sin límite de intentos de login ni *timing* uniforme en usuario
  desconocido; (5) tokens de sesión en claro en `sessions`; (6) `POST /api/analyses` y `POST /api/assistant`
  siguen sin exigir sesión — no están en la lista protegida de S1; (7) `GET /api/status` ahora expone
  `created_by: null` por lote (consecuencia inherente de la columna pedida).
- **L14** · **Segundo corte de T1** (autoría + `downloads` + `audit_log` + cuota). **RED observado**:
  `tests/test_downloads.py` → `11 failed` (`TypeError` por el parámetro `created_by` inexistente y `404` en
  las rutas nuevas). **GREEN observado**: `python -m pytest -q` → **`56 passed`** (45 + 11),
  `npm --prefix web run build` → `✓ built in 4.33s`, `openapi.json` con `/api/downloads` y `/api/audit`.
- **L15** · Commit `e374477` — **324 líneas autorizadas** (318 + 40 − 34 de `openapi.json` generado), dentro
  del presupuesto de 400 de WORK_PLAN §8.
- **L16** · El fixture `client` compartido se movió a `tests/conftest.py` (variante **anónima**) para que
  `test_auth.py` y `test_downloads.py` no dupliquen la preparación de la base; `tests/test_nina.py` conserva su
  propia variante **autenticada** y la sombrea solo en ese módulo. Los helpers de datos (`fixture_csv`, `seed`,
  `selection`) se **reutilizan** desde `test_nina`, no se reescriben.
- **L17** · Decisiones de alcance: la auditoría registra solo operaciones **aceptadas** (job en cola), no
  intentos rechazados; `/api/acquisitions*` y `/api/sync` quedan cableados igual que `import`/`train` pero sus
  tests excluirían red, así que se cubren con `import` y `train`. **Queda pendiente** el tope de *filas* por
  exportación (`MAX_EXPORT_ROWS`) y el resto de advisories de L13.
- **L18** · **Verificación independiente** (`gentle-ai-verify`) sobre `e374477` → **`pass`, 9/9 checks,
  cero blockers**. Aislamiento entre usuarios de `/api/downloads` comprobado en ambos sentidos (intersección
  de conjuntos vacía); `/api/audit` legible solo por `admin` y sin otro lector en `nina/`, `scripts/` ni
  `web/src`; auditoría **sin filas** en peticiones rechazadas (409/422) y con fila `queued` en las aceptadas;
  cuota leída **por petición** y **por usuario**; esquema aditivo `PROBLEMS: none`; `openapi.json`
  byte-idéntico al regenerar. Spot check del padre: `56 passed` ✅.
- **L19** · **Advisories del segundo verificador → van en el corte de la web** (los bytes verificados no se
  tocan): (1) **`GET /api/status` es anónimo y ahora expone `batches[].created_by` con un UUID real** — es el
  único hallazgo con cara de divulgación y conviene ocultarlo ahí; (2) `MAX_DOWNLOADS_PER_HOUR='abc'` produce
  un `500` sin capturar (leer el valor con respaldo a valor por defecto); (3) `openapi.json` no documenta
  `401`/`403` en ninguna ruta — estilo previo, no regresión; (4) `MAX_EXPORT_ROWS` sigue sin implementarse;
  (5) `manifest`/`report` registran `rows=0` en `downloads`.
- **L20** · **Celda C (web)** en `003a86a`. Un solo diálogo `web/src/Account.tsx` con tres vistas:
  **formulario** (login/registro con rol `visitante`/`analista`), **perfil** y **"Mis descargas"**; más una cuarta
  vista **Auditoría** reservada a `admin`. `App.tsx` carga `/api/auth/me` al arrancar y es la única dueña del
  estado de sesión que comparten `Dialog` y `DataPanel`. Estados sin permiso: la lista de exportaciones se
  sustituye por un aviso con acceso directo al inicio de sesión, y en `DataPanel` importar/sincronizar/entrenar
  quedan deshabilitados con explicación para quien no es `admin`. Verificación: `tsc -b && vite build` en verde
  (`✓ built in 4.03s`) y suite de Python **`56 passed`** (el backend no se tocó).
- **L21** · **El criterio de aceptación de T1 queda cubierto**: "un visitante no puede importar ni exportar" (servidor
  + interfaz), "un analista ve su historial" (vista "Mis descargas"), "un admin ve la auditoría" (vista "Auditoría",
  añadida en `003a86a` porque solo existía el endpoint y faltaba la pantalla).
- **L22** · **PR #1 abierto hacia `mvp-abraham`** (<https://github.com/Abraham-ch/Nina/pull/1>) con los 6 primeros
  commits. **Advertido en el cuerpo del PR**: 819 líneas autorizadas contra el tope de 400 de §8, con la oferta de
  partirlo en dos PRs apilados (`c6721fc` y `d879306` vienen separados) sin tocar el contenido.
- **L23** · `Risk: item 6` para la entrega de la interfaz — **`web/` no tiene ningún test**; la única red es
  `tsc -b && vite build` (§15 del `AGENTS.md` raíz lo admite como verificación mínima del área). Corresponde
  verificador independiente.
- **L24** · **Conflicto con `mvp-abraham` resuelto por rebase** (decisión del usuario: "resolvell"). El PR #1
  salía `CONFLICTING`/`DIRTY` porque `mvp-abraham` avanzó 3 commits mientras trabajaba: `e12d7d0`
  (*bilingual UI, oxfmt formatting*) reescribió `App.tsx` (+1.253 líneas), `Dialog.tsx` (476) y
  `DataPanel.tsx` (445), añadió `web/src/i18n.ts` (**inglés por defecto**, `tr(en, es)`), `oxfmt`
  (2 espacios, comillas simples, sin punto y coma) y `landing/`, `LangSwitch.tsx`, `Tour.tsx`; más
  `a7a562c` (documentación al inglés) y `19c80a6` (tour e indicadores).
- **L25** · **Resolución**: los 5 archivos en conflicto eran todos `web/src/`; **el backend no tuvo ningún
  conflicto**. Estrategia: tomar la base de Abraham en `App`/`Dialog`/`DataPanel`/`style.css` y **reaplicar**
  encima la celda C, ahora con `tr(en, es)` en cada cadena visible y `locale()` en fechas; `types.ts` =
  base + mis 6 tipos + `Batch.created_by`. `oxfmt` aplicado, `--check` limpio.
- **L26** · **`4c791e9` quedó absorbido** en `003a86a`: la vista "Auditoría" ya venía dentro de `Account.tsx`
  reescrito, el replay quedó vacío y se descartó. **Todos los hashes cambiaron** tras el rebase:
  `fb8ff88→54f718a` · `a0438d5→c6721fc` · `81987ea→0600e65` · `e374477→d879306` · `cd5b826→325f335` ·
  `b215fbc→78dc774` · `ddb6be4→665906e` · `b9681da+4c791e9→003a86a` · `e6a0726→f7a2a8c`.
- **L27** · **Verificación tras el rebase**: `oxfmt --check` limpio · `tsc -b && vite build` → `✓ built in
  3.95s` · `pytest` → **`56 passed`**. Rama de seguridad `backup/anthony-tasks-pre-rebase` (`e6a0726`).
  **Pendiente**: el `push --force-with-lease` lo tiene que correr la persona, el sandbox del agente lo bloquea.
- **L28** · **Tercer verificador** sobre `003a86a` → **`advisories`, 0 blockers**, 6/6 ítems cumplidos:
  gates en verde, nada perdido en el rebase, i18n conforme a §13, lógica reaplicada balanceada, 31/31
  probes de enforcement en el servidor con la base **byte-idéntica tras cada rechazo**, y cero solape de
  líneas entre mis commits de backend y los de Abraham.
- **L29** · **3 defectos míos del rebase corregidos** en `c78fb0f`: el `aria-label` del botón de cuenta
  usaba un prefijo en inglés crudo (lectores de pantalla en español anunciaban inglés), el `placeholder`
  del correo no estaba en `tr()`, y el perfil decía "descargas en la última hora" mostrando todo el
  historial y solo cargándolo al entrar en "Mis descargas".
- **L30** · **PR #1 mergeado** por Abraham (`761ea27`, 23:58Z) — pero **antes** de `c78fb0f`, así que ese
  commit quedó huérfano. Rama resincronizada con `git rebase origin/mvp-abraham` (`4dcd59c → c78fb0f`),
  ahora **1 adelante / 0 atrás**. Se necesitaba force-push: el sandbox del agente lo bloquea, lo corrió la
  persona.
- **L31** · **Tests de matriz de enforcement** en `tests/test_auth_matrix.py` (`5bf79b7`) — **8 tests
  nuevos, suite `56 → 64 passed`**. Ambos verificadores los habían propuesto y nadie los había escrito;
  cerraban de verdad el `Risk: item 6` del backend de T1. **El primer intento FALLÓ**: medía el hash de la
  base *antes* de los registros, que sí escriben. Corregido midiendo **después** de montar la sesión y
  añadiendo un **control** (una operación legítima debe cambiar el hash) para que el test no pueda pasar
  en vacío. `Risk: none` — solo añade pruebas, no toca comportamiento.
- **L32** · **Deriva de fuente detectada**: `a7a562c` (en la base desde el rebase) tradujo
  `WORK_PLAN.md` al inglés — §10 hoy es *"Cross-cutting product tasks (leadership tasks)" / "T1 · Users
  and download management"*. Los specs **S1–S3 de este documento siguen citando la versión en español
  vigente en `90d2ed6`**, que es la que se usó para escribir el trabajo. **El contenido es el mismo**,
  solo cambió el idioma: no se re-escriben los `S#` (no sería *verbatim* de ninguna de las dos fuentes),
  pero quien compare contra el `WORK_PLAN.md` actual debe saber que está viendo una traducción.
- **L33** · **`MAX_EXPORT_ROWS` + advisories de seguridad** en `0245a72`. **RED observado**: 6 tests
  nuevos fallando (`200 == 413`, `created_by` a la vista, `attach()` sin `secure`, 200k < 600k,
  `ValueError` con `'abc'`, `openapi` sin `401`); los 2 tests de regresión ya pasaban (el límite por
  debajo del tope y los hashes escritos a 200k). **GREEN**: `72 passed` (64 + 8), build `✓ built in
  4.12s`, `oxfmt --check` limpio. **165 líneas autorizadas** (147 + 18, sin `openapi.json`).
  Cerrado: cuota de filas por exportación con `413` y mensaje con el tope · `GET /api/status` ya no
  proyecta `created_by` (`SELECT * EXCLUDE`), el valor sigue en la base y **cero lectores** en
  `web/src` · cookie `Secure` condicionada al esquema de la petición · PBKDF2 **200k → 600k** (OWASP
  2023) con test de que los hashes viejos siguen verificando · `MAX_DOWNLOADS_PER_HOUR='abc'` cae al
  valor por defecto en vez de un `500` · las 8 rutas protegidas declaran `401`/`403` en `openapi.json`.
  **`Risk: item 2`** (cookie `Secure` y rondas de PBKDF2) **e `item 3`** (se retiró el campo
  `batches[].created_by` de la respuesta de `/api/status`; era el leak y no tenía ningún lector).
- **L34** · **Cuarto verificador** sobre `0245a72` → **`advisories`, 0 blockers**. 47 probes propios en
  verde, **control positivo sobre la base** (`14 BASE-EXISTS / 0 absent`: en `db0a64b` el leak existía,
  la cookie no tenía `Secure`, `MAX_EXPORT_ROWS` se ignoraba, eran 200k rondas, `'abc'` reventaba con
  `500` y `openapi` solo declaraba `200`), regresión `64 ⊂ 72` sin ids perdidos, `openapi.json`
  byte-idéntico al regenerar, y **cero lector** de `batches[].created_by` en `web/src`, `scripts/` ni
  `docs/`.
- **L35** · **1 advisory corregido** en `9d65cba`: `SELECT * EXCLUDE (created_by)` falla al hacer *bind*
  si la columna no existe, y `scripts/check_release.py` es el único llamante de `status()` que **no**
  pasa por `initialize()` — una base anterior a T1 habría reventado, contra la regla de `nina/AGENTS.md`
  "nunca romper bases existentes". Ahora consulta `information_schema` antes y cae a `SELECT *`, con
  test. **`73 passed`**, build y formato verdes. `Risk: none` — solo añade una red de seguridad en la
  ruta de lectura.
- **L36** · **Brecha conocida y fuera de este PR**: las descargas son enlaces `<a href>`, así que un
  `413`/`429`/`401` se muestra como **JSON crudo** en el navegador. El mensaje del servidor es claro y
  en español, pero la UI no lo enmarca. Lo dejó el verificador en `unverified` (habría que *clickear*);
  corregirlo implica convertir los enlaces de exportación en `fetch` + aviso, y es una pieza de
  interfaz aparte. **También pendiente**: `manifest`/`report` registran `rows=0`.
- **L37** · **La target branch cambió a `mvp`** (instrucción del usuario). Verificado con `merge-base`:
  `mvp` **contiene** a `mvp-abraham`, absorbió los dos PRs mergeados (`d3ef1c7`), y suma 10 commits —
  API de lectura `harmonized`, `packages/nina/` (pipeline offline con H3+uv, ADR 0002–0004), ADRs,
  `fly.toml` y `openapi.d.ts`. Mi rama iba 1 atrás / 1 adelante.
- **L38** · **Cambio de requisito detectado al mirar el spec vigente.** El `WORK_PLAN.md` §10 ya **no**
  pide el mensaje *en español*; pide:
  > *"Uniform errors: a `422` response with a `code` and a message (_problem+json_ style), shown as is in the UI, **in the interface language**."*

  Reescrito el bullet de `S2` con ese texto verbatim. Consecuencias implementadas: `nina/errors.py`
  lleva **cada regla y cada plantilla de Pydantic en los dos idiomas** y elige por `Accept-Language`
  (por defecto **inglés**, igual que `i18n.ts`); `web/src/api.ts` manda esa cabecera; el `code` **no**
  cambia con el idioma porque es contrato. Tres `ValueError` a secas de `Selection` pasaron a tener code
  (`department_unknown`, `scope_mismatch`, `geometry_required`), lo que cierra el advisory 1 del cuarto
  verificador (el mensaje concreto se perdía en un "Entrada inválida" genérico).
- **L39** · **Merge de `origin/mvp` en `anthony/tasks`** (`e45ae7a`): 2 conflictos resueltos —
  `nina/analytics.py` (el validador de `Selection`) y `nina/main.py` (`app=FastAPI` + `instalar(app)`) —
  conservando **mi estructura con códigos y sus textos en inglés**. Verificación de que nada se perdió:
  `git diff --cached origin/mvp` sobre esos dos archivos da **45+/16−**, todo mío; `harmonized_router`
  y el resto de aportes de `mvp` siguen presentes. **`openapi.json` regenerado** (las rutas nuevas de
  `harmonized` entraron con el `422` viejo `HTTPValidationError`; ahora apuntan a `Problem`).
- **L40** · **3 archivos de `mvp` no pasan `oxfmt`** (`Experiment.tsx`, `perf-scene.js`, `landing/Landing.tsx`).
  El formatter los tocó y **los revertí a propósito**: reformatarlos aquí enterraría el merge en ruido
  ajeno y `format:check` no es una puerta del CI. **Queda como deriva preexistente de `mvp`.**
  Verificación del merge: **`98 passed`**, build `✓ built in 4.09s`. `Risk: none` — el merge solo
  resuelve conflictos y añade el soporte de idioma que pide el spec, todo cubierto por tests.
- **L41** · **Celda A de T2** en `ae69bc8`. **RED observado**: `tests/test_coverage.py` → **8 fallaban**
  (faltaban `store.cobertura`, los códigos de cobertura, el futuro en la importación y `dias_maximos`);
  **GREEN**: **`11 passed`**, suite completa **`109 passed`** (98 → 109), build verde, `openapi.json`
  **sin cambios** al regenerar (ninguna firma de ruta cambió). `Risk: none`.
  Implementado: `store.cobertura(source)` = `min/max(acquired)` por origen, con fechas nulas si no hay
  filas (no se acota lo que no existe) · `_cobertura_inicio` rechaza pedir antes del primer día observado
  del sensor, y `_cobertura_mes` solo rechaza si el **mes entero** precede, así un primer mes parcial sigue
  siendo válido · aplicado a `/api/sync`, `/api/acquisitions` y `/api/acquisitions/month` vía la tabla
  `ORIGEN_PRODUCTO` — "NOAA-21 solo desde 2024" sale de los datos, no de una regla escrita dos veces ·
  `/api/import` ya no acepta `coverage_start` futuro (gap detectado por el verificador) y un rango invertido
  da `date_range`, el bullet "`start ≤ end`" de §10 en la única superficie que tiene las dos fechas hoy ·
  `FIRMS_MAX_DAY_RANGE` (estaba en `.env.example` **sin que nada lo leyera**) acota ahora `days`.
- **L42** · **Descubrimientos técnicos**: (1) `PydanticCustomError(code, plantilla, contexto)` **no** acepta
  keywords — el contexto va como **tercer argumento `dict`** y llega a `err['ctx']`; probado a mano antes de
  corregir las 4 llamadas. (2) `fixture_csv` no produce un CSV que `ingest_file` acepte como VIIRS, así que
  el test de cobertura de NOAA-21 inserta la fila directo: en la celda A lo que importa es la cobertura de
  la base, y la ingesta tiene sus propios tests.
- **L43** · **Alcance acotado de T2**: "nada posterior al último día disponible" **no** se aplica a las
  descargas — pedir datos nuevos es justamente el propósito de `/api/sync`, y el último día *disponible*
  sale de `data_availability` (§9 / ING-09, que aún no existe). Pertenece a las consultas de rango libre de
  **T3**. **Queda de T2**: la celda C (validación en formularios, selector de fechas acotado por la
  cobertura, mensaje junto al campo) y el bullet de CSV con columnas FIRMS obligatorias y UTF-8.
