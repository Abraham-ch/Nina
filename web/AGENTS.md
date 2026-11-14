# AGENTS.md · Rol C — Web (`web/`)

> Prevalece sobre el `AGENTS.md` raíz para los archivos de esta carpeta. Reparto completo en `WORK_PLAN.md` §2.

## Puedes escribir

- `web/**`, `design/**`, `nina-demo.html`, `.nvmrc`.

## No escribas

`nina/**`, `scripts/**`, `tests/**`, `openapi.json`, `data/**`, dependencias Python, Docker, lanzadores, `.github/**`.
Si necesitas un cambio en la API: `docs/requests/api-<slug>.md`.

## Reglas del área

- React + Vite + TypeScript `strict` + CesiumJS. Dependencias con `npm.cmd --prefix web install <pkg>` (commitea
  `package-lock.json`; nunca lo edites a mano).
- Los tipos de la API viven solo en `src/types.ts` y las llamadas en `src/api.ts`; deben coincidir con `openapi.json`.
  Si no coinciden, pide el cambio a B, no adaptes la respuesta en el componente.
- Trabaja contra el servidor local (`.\start-nina.ps1`) con datos reales; `npm.cmd --prefix web run dev` para desarrollo.
- Las observaciones se muestran identificadas por instrumento/plataforma; nunca sumes sensores en la interfaz.
- Hueco ≠ parcial ≠ cero: un hueco nunca se pinta como 0 (gris con trama); parcial y provisional, distinguibles.
- Cita y aviso de FIRMS visibles (AGENTS §11); atribución de cartografía en `public/assets/attribution.json`.
- Un componente por archivo en `src/`; si un archivo crece demasiado, divídelo en una carpeta por funcionalidad.
- Funciones a medio terminar, detrás de `VITE_FEATURE_*`.

## Verificación

```powershell
npm.cmd --prefix web run build
```

Commits: `feat(web): …` · Ramas: `web/<slug>`.
