# AGENTS.md · Rol C — Web (`apps/web`, `packages/ui`, `packages/config`)

> Prevalece sobre el `AGENTS.md` raíz para los archivos de estas carpetas. Lee también `WORK_PLAN.md` y
> `apps/api/API_CONTRACT.md` (Parte A).

## Puedes escribir

- `apps/web/**`, `packages/ui/**`, `packages/config/**`.
- Tu sección de `.env.example` (`# --- C · web ---`).

## No escribas

`apps/api/**`, `packages/nina/**`, `pipelines/**`, `packages/schemas/**` (incluidos los tipos generados), `infra/**`,
`.github/**`, configuración raíz, lockfiles. Si necesitas un cambio en la API: `docs/requests/api-<slug>.md`.

## Reglas del área

- Los tipos de la API vienen solo de `@fire/schemas` (generados); no declares a mano tipos de respuestas.
- Mientras un endpoint no exista, usa los mocks MSW de `apps/web/src/mocks/` (hechos con los `examples` del contrato).
- Una carpeta por funcionalidad en `src/features/`; las rutas viven en `src/app/`. Un componente que se use en más de una
  feature va a `@fire/ui`.
- Sin lógica de sensor: nunca muestres `source_mix` fuera de "Detalles del dataset" (AGENTS §10.4).
- Pie con cita y aviso de FIRMS siempre visible (AGENTS §11), con los textos de `@fire/schemas`.
- `data_gap` nunca se pinta como 0 (gris con trama); `is_provisional` con borde punteado (AGENTS §13).
- Funciones a medio terminar: detrás de `VITE_FEATURE_*`.

## Verificación

```bash
pnpm turbo run lint typecheck build --filter=@fire/web --filter=@fire/ui
```

Commits: `feat(web): …`, `feat(ui): …` · Ramas: `web/<slug>`.
