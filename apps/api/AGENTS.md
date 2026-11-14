# AGENTS.md · Rol B — API y plataforma (`apps/api`)

> Prevalece sobre el `AGENTS.md` raíz para los archivos de esta carpeta. El contrato está en `API_CONTRACT.md`
> (esta carpeta); el reparto de trabajo en `WORK_PLAN.md`.

## Puedes escribir

- `apps/api/**`, `packages/schemas/legal/**`, `packages/schemas/{package.json,tsconfig.json,src/index.ts}`.
- `infra/**`, `.github/**`, configuración raíz (`package.json`, `turbo.json`, `pnpm-workspace.yaml`, `pyproject.toml`).
- Tu sección de `.env.example` (`# --- B · API/infra ---`).

## No escribas

`packages/nina/**`, `pipelines/**`, `packages/schemas/db/**`, `packages/schemas/json/**`, `apps/web/**`,
`packages/ui/**`, `packages/config/**`. Si necesitas algo ahí: `docs/requests/<rol>-<slug>.md`.

## Reglas del área

- Sin lógica de sensor (AGENTS §2.1): solo se lee el esquema `serving`. De `nina` solo se importan `nina.config` y `nina.stats`.
- Estructura: `routers/` (un archivo por endpoint; solo validan y llaman a servicios) · `services/` · `db/` · `models.py`.
  `main.py` solo crea la app y monta routers.
- `models.py` es la frontera con la web: todo modelo de respuesta lleva `examples`. Al cambiarlo, ejecuta
  `pnpm gen:types` y commitea `packages/schemas/openapi/openapi.json` y `src/generated/api.ts` en el mismo PR `contract:`
  (revisa C). Actualiza `API_CONTRACT.md` y su historial.
- Nunca leas `source/`: trabaja contra el seed (`packages/schemas/db/seed/`).
- Los textos de cita y aviso salen de `packages/schemas/legal/firms.json`.

## Verificación

```bash
pnpm turbo run lint typecheck --filter=@fire/api --filter=@fire/schemas --filter=@fire/web
```

(`@fire/web` se incluye para detectar a tiempo si un cambio de modelos rompe los tipos de la web.)

Commits: `feat(api): …`, `chore(infra): …`, `contract: …` · Ramas: `api/<slug>`, `infra/<slug>`, `contract/<slug>`.
