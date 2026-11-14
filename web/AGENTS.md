# AGENTS.md · Role C — Web (`web/`)

> Takes precedence over the root `AGENTS.md` for files in this folder. Full split of responsibilities in `WORK_PLAN.md` §2.

## You may write

- `web/**`, `design/**`, `nina-demo.html`, `.nvmrc`.

## Do not write

`nina/**`, `scripts/**`, `tests/**`, `openapi.json`, `data/**`, Python dependencies, Docker, launchers, `.github/**`.
If you need an API change: `docs/requests/api-<slug>.md`.

## Area rules

- React + Vite + TypeScript `strict` + CesiumJS. Dependencies via `npm.cmd --prefix web install <pkg>` (commit
  `package-lock.json`; never edit it by hand).
- API types live only in `src/types.ts` and calls in `src/api.ts`; they must match `openapi.json`.
  If they do not match, ask B for the change; do not adapt the response inside the component.
- Work against the local server (`.\start-nina.ps1`) with real data; `npm.cmd --prefix web run dev` for development.
- Observations are always shown identified by instrument/platform; never add sensors together in the interface.
- Gap ≠ partial ≠ zero: a gap is never painted as 0 (grey with hatching); partial and provisional must be distinguishable.
- FIRMS citation and warning visible (AGENTS §11); cartography attribution in `public/assets/attribution.json`.
- Interface text is bilingual (English by default, Spanish available) through `tr()` in `src/i18n.ts`.
- One component per file in `src/`; if a file grows too large, split it into a folder per feature.
- Half-finished features go behind `VITE_FEATURE_*`.

## Verification

```powershell
npm.cmd --prefix web run build
```

Commits: `feat(web): …` · Branches: `web/<slug>`.
