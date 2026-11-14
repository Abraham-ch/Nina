# AGENTS.md · `nina/` — Roles A (procesamiento) y B (API)

> Prevalece sobre el `AGENTS.md` raíz para los archivos de esta carpeta. Reparto completo en `WORK_PLAN.md` §2.
> `nina/` es un solo paquete: **la propiedad es por archivo**.

## Quién escribe qué

| Archivo | Dueño |
|---|---|
| `ingest.py`, `global_ingest.py`, `remote.py`, `science.py`, `store.py` | **A** (cambios en `store.py` los revisa B) |
| `main.py`, `analytics.py`, `assistant.py`, `config.py` | **B** (cambios en `config.py` los revisa A) |

Fuera de `nina/`: A también escribe `scripts/` (salvo `export_openapi.py`), `data/boundaries/`, `docs/reference/`,
`notebooks/`, `tests/test_global_ingest.py`. B también escribe `openapi.json`, `scripts/export_openapi.py`, el resto de
`tests/`, dependencias, Docker, lanzadores y `.github/`. Nadie de A/B escribe `web/**`. Si necesitas algo de otro dueño:
`docs/requests/<rol>-<slug>.md`.

## Reglas del paquete

- La lógica específica de sensor (origen, normalización, precedencia SP/NRT, exclusión de Landsat) solo en los
  módulos de A. `analytics.py` y `main.py` consumen la base, no reinterpretan los originales.
- Acceso a DuckDB solo con `store.database()` / `atomic_read`. Columnas nuevas: `ALTER TABLE … ADD COLUMN IF NOT EXISTS`
  en `initialize()`, nunca romper bases existentes.
- Un solo proceso escribe la base: las importaciones de consola usan `--data-dir data/<staging>` o el servidor detenido.
- Rutas solo en `main.py`; la lógica, en `analytics.py`. Al cambiar rutas o modelos: `scripts/export_openapi.py` y avisar a C.
- Toda fila descartada se cuenta (`rejected`, `duplicates`, `excluded_files`).
- Hueco ≠ parcial ≠ cero en todo resultado.
- Originales en `source/`: estáticos del equipo en la raíz (entrada de `scripts/import_global.py`, ámbito mundial) y todo lo
  descargado o subido en `config.RAW` (`source/downloads/`). Nunca guardes descargas en la raíz de `source/` ni en `data/`.
  Los derivados van en `config.DATA` (`data/`).

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/export_openapi.py   # si cambió la API; commitear openapi.json
```

Commits: `feat(nina): …` (A), `feat(api): …` / `fix(api): …` (B) · Ramas: `nina/<slug>`, `api/<slug>`.
