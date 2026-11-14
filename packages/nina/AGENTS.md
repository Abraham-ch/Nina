# AGENTS.md · Rol A — Procesamiento (`packages/nina`)

> Prevalece sobre el `AGENTS.md` raíz para los archivos de esta carpeta. Lee también `WORK_PLAN.md` y
> `apps/api/API_CONTRACT.md` (Parte B).

## Puedes escribir

- `packages/nina/**`, `notebooks/**`, `packages/schemas/json/**`, `packages/schemas/db/**` (DDL, migraciones, seed).
- `pipelines/**` solo desde la Fase 3 (WORK_PLAN §4).
- Tu sección de `.env.example` (`# --- A · nina ---`).

## No escribas

`apps/**`, `packages/ui/**`, `packages/config/**`, `packages/schemas/openapi/**`, `packages/schemas/src/**`,
`packages/schemas/legal/**`, `infra/**`, `.github/**`, configuración raíz, lockfiles. Si necesitas algo ahí:
`docs/requests/<rol>-<slug>.md`.

## Reglas del área

- Los datos FIRMS se leen de `source/` (gitignored); las salidas van a `source/interim/`, `source/harmonized/` y `source/reports/`.
- I/O solo en `src/nina/io/`; el resto son funciones puras (AGENTS §16).
- `src/nina/stats.py` y `config.py` los consume la API: cambios en sus firmas = PR `contract:` revisado por B.
- Cambios en `packages/schemas/db/**` (frontera A→B) requieren la aprobación de B y actualizar el seed.
- Cumple `ACCEPTANCE_CRITERIA.md`; los tests y el reporte de aceptación se exigen desde la Fase 3.

## Verificación

```bash
pnpm turbo run lint typecheck --filter=@fire/nina
```

Commits: `feat(nina): …` · Ramas: `nina/<slug>`.
