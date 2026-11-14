# NINA 0.3: archivo mundial procesado

La aplicación utiliza una base mundial procesada y verificada. El alcance del MVP es **2025–2026**. Los nueve archivos de `source/` (en la máquina original, `data_abraham/`) utilizados cubren detecciones del **5 de noviembre de 2025 al 13 de noviembre de 2026**, según instrumento; también se conserva la instantánea mundial del 14 de noviembre previamente descargada.

## Datos incorporados

- **59.440.077 observaciones únicas en la base activa.**
- **57.332.047 filas nuevas** de las fuentes mundiales del equipo.
- **9 archivos verificados**, equivalentes a 23.54 GB de originales.
- **18.855 duplicados técnicos** descartados y **19 filas inválidas** registradas con motivo.
- Landsat se excluyó como archivo identificado; el alcance es MODIS y VIIRS.

| Fuente | Filas nuevas incorporadas |
|---|---:|
| MODIS Terra + Aqua | 3.474.789 |
| VIIRS S-NPP | 17.456.430 |
| VIIRS NOAA-20 | 18.586.456 |
| VIIRS NOAA-21 | 17.814.372 |

El total de la base también incluye las 2.108.030 observaciones de la entrega anterior. Los conteos son observaciones por instrumento; no representan incendios individuales distintos.

## Tamaño y ejecución

Base DuckDB: **2.24 GB**. Copia Parquet: **1.87 GB**, con las mismas 59.440.077 filas. Los originales se conservan en `source/` (en la máquina original, `data_abraham/`); no se copiaron al cliente ni se subieron a Git.

La importación usa dos trabajadores de consulta DuckDB y un límite de memoria de 1 GB por conexión de ingesta, procesando archivos y meses por turnos. Las consultas usan por defecto un límite de 2 GB. El mapa entrega como máximo 10.000 puntos, y el comparador 8.000 por instrumento; los conteos y exportaciones utilizan todas las filas seleccionadas.

## Consultas comprobadas fuera de Perú

Julio de 2026, VIIRS NOAA-20, sobre las geometrías Natural Earth de referencia:

| Territorio | Detecciones |
|---|---:|
| Brasil | 39.356 |
| Australia | 124.368 |
| Indonesia | 24.028 |
| Estados Unidos | 92.794 |
| R. D. del Congo | 364.618 |

En cada caso se comprobó que el total del mapa coincide con el análisis. La copia Parquet se verificó contra la base y no se encontraron identificadores duplicados. Se comprobaron los hashes de los nueve originales y el balance de filas aceptadas y excluidas. Las 33 pruebas de backend, la compilación web y las nueve tareas de lint y tipos del monorepo pasaron.

Se verificaron también la API y el navegador con la base activa: calendario mundial, conteos, muestra de puntos, comparación fuera de Perú, exportación CSV, manifiesto, explicación y presentación móvil. Los meses anteriores que solo tienen registros regionales peruanos no rellenan el calendario mundial cuando ya existen lotes mundiales.

## Abrir y reproducir

Desde la raíz del repositorio:

```powershell
.\start-nina.ps1
```

Abrir `http://127.0.0.1:8000/`. La entrada principal abre el calendario mundial. La selección inicial es julio de 2026 con NOAA-20; se puede cambiar de país, mes o instrumento. El período y los archivos reales aparecen en Fuentes.

Los reportes locales están en `data/global-import.json` y `data/release-world-v0.3.json`. La versión anterior de la base se conserva en `data/backups/before-world-*/`. [Decisión de alcance y comandos de procesamiento](ALCANCE_MUNDIAL.md).

## Límites que siguen vigentes

El período mundial disponible no alcanza cinco años de referencia; no se inventan medianas o anomalías mundiales. El histórico peruano anterior se conserva como conjunto regional.

Las fechas de los registros no certifican oportunidades de observación ni ausencia de nubes. El calendario conserva estados parciales o de integridad desconocida y no convierte áreas sin soporte en ceros. La armonización científica mundial y su validación permanecen pendientes; el experimento de calibración sigue limitado al caso peruano.
