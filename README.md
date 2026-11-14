# Ejecutar el MVP local

La aplicación funcional de la rama `mvp` está en **[`mvp/`](mvp/README.md)**. Sus instrucciones de instalación, descarga de datos y API están en ese README.

```bash
git clone --branch mvp --single-branch https://github.com/Abraham-ch/Nina.git
cd Nina/mvp
```

En Windows, con Python 3.14 y Node.js 22:

```powershell
.\setup-nina.ps1
.\start-nina.ps1
```

Abrir http://127.0.0.1:8000. Para descargar además el histórico público de Perú, detener el servidor y ejecutar `setup-nina.ps1 -DownloadData`.

El MVP conserva observaciones por instrumento y calibraciones exploratorias. La armonización científica descrita a continuación sigue siendo el objetivo del monorepo.

---

# Fire Calendar — Harmonized MODIS + VIIRS Hotspots

An initiative focused on **harmonizing MODIS and VIIRS satellite fire detections** to improve the
consistency and reliability of hotspot data. Built for the **NASA Space Apps Challenge**.

## Why

NASA FIRMS publishes active-fire detections from two instrument families:

- **MODIS C6.1** (Terra/Aqua, ~1 km) — the long record, since 2000.
- **VIIRS 375 m C2** (S-NPP, NOAA-20, NOAA-21) — finer detail, since 2012.

VIIRS sees many more hotspots than MODIS over the same fire, so simply concatenating both records
creates an artificial jump in 2012. That makes it hard to answer a basic question: *is this fire
season actually unusual?*

## What it does

1. **Harmonization** — ingests FIRMS data, applies quality control (confidence, static sources,
   standard vs. NRT precedence, known data gaps), counts active H3 cells instead of raw pixels, and
   calibrates MODIS to "VIIRS-equivalent" units using the 2012+ overlap period. After this step the
   source sensor no longer matters.
2. **Web app** — pick a region and a date range to get:
   - a fire **activity calendar** (year × month heatmap, counts or anomalies),
   - time series against the climatological band and a ranking of years,
   - **CSV downloads** of hotspots and aggregates.

Data gaps are shown as gaps, never as "no fire activity".

## Repository

| Path | Contents |
|---|---|
| `AGENTS.md` | Full technical spec: data contract, QA rules, harmonization method, API, frontend |
| `packages/nina/ACCEPTANCE_CRITERIA.md` | What "done" means |
| `docs/DATA_SOURCES.md` | Data sources used |
| `docs/` | Architecture diagram, methodology, ADRs |
| `source/` | All data (gitignored): raw FIRMS `fire_archive_*` / `fire_nrt_*` JSON + CSV, and derived outputs |

## Disclaimer

Data from NASA FIRMS. Because of their spatial resolution, FIRMS does not recommend these data for
tactical or local-scale decisions — this calendar is a tool for **historical context**.
See the [FIRMS disclaimer](https://www.earthdata.nasa.gov/data/tools/firms).
