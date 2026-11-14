# NINA: alcance mundial del MVP

## Decisión de período

El MVP mundial utiliza **2025–2026**, limitado a las fechas efectivamente incorporadas. Los archivos del equipo comienzan el **5 de noviembre de 2025**; el corte reciente se amplía con el CSV MODIS de siete días y las ventanas ya descargadas por la API.

La selección inicial es **julio de 2026 y VIIRS NOAA-20**, un mes incluido en los archivos estándar de MODIS, S-NPP, NOAA-20 y NOAA-21. Se puede cambiar de mes, país, instrumento o área dibujada.

Se eligió este período porque aprovecha el conjunto mundial ya disponible, incluye una vuelta aproximada por las estaciones del año y permite probar varios instrumentos sin descargar décadas completas. Los originales mundiales ocupan decenas de GB; el procesamiento por bloques y el almacenamiento analítico evitan cargarlos juntos en memoria.

**Este alcance permite demostrar exploración mundial. Para construir referencias históricas mundiales se necesitan más años.** No se calcula una anomalía contra cinco años donde solo existe aproximadamente uno. La ampliación histórica debe priorizar las áreas de interés y reutilizar agregados, en lugar de descargar inmediatamente todos los originales mundiales desde 2000.

El histórico peruano 2000–2025 se conserva como conjunto regional. No se presenta como historia mundial.

## Entradas utilizadas

Los originales permanecen en `data_abraham/`, fuera de Git:

| Archivo o grupo | Contenido |
|---|---|
| `fire_archive_M-C61_844123.json` | MODIS Terra/Aqua estándar |
| `fire_archive_SV-C2_844126.json` | VIIRS S-NPP estándar |
| `fire_archive_J1V-C2_844124.json` | VIIRS NOAA-20 estándar |
| `fire_archive_J2V-C2_844125.json` | VIIRS NOAA-21 estándar |
| Cuatro archivos `fire_nrt_` de esos instrumentos | Registros provisionales posteriores |
| `MODIS_C6_1_Global_7d.csv` | Actualización reciente de MODIS |
| `fire_nrt_LS_844122.json` | Landsat: excluido del alcance MODIS/VIIRS y registrado como archivo excluido |

Se contrastaron nomenclatura, separación estándar/NRT, coordenadas WGS84 y uso de los datos con el [Readme oficial de FIRMS](https://firms.modaps.eosdis.nasa.gov/download/Readme.txt). Para disponibilidades actuales se usa además el catálogo FIRMS: el Readme contiene una nota sobre ausencia de productos estándar NOAA-20/21 que no coincide con los archivos entregados y el catálogo consultado; no se utiliza esa nota como regla fija del programa.

## Qué procesamiento se aplica

1. Leer CSV y JSON con memoria acotada; conservar los originales.
2. Identificar instrumento y plataforma, normalizar fecha/hora UTC y coordenadas.
3. Comprobar fechas, coordenadas, confianza y campos numéricos. Registrar el motivo de cada exclusión y fallar si más del 1 % son inválidos.
4. Identificar duplicados técnicos y aplicar prioridad de estándar sobre NRT en su ámbito. Esto evita sumar revisiones de una observación como si fueran nuevas detecciones.
5. Incorporar las detecciones de todo el mundo. La asignación a divisiones peruanas solo es un atributo adicional; los puntos de otros territorios se conservan.
6. Consultar por fuente, territorio y mes. Para países se filtra la geometría de referencia exacta, después del filtro rectangular.
7. Mostrar conteos completos y una muestra limitada de puntos en el mapa. Exportar todas las observaciones seleccionadas por bloques.

La ingesta conserva detecciones de distintos tipos y niveles de confianza; no declara que cada punto sea un incendio forestal. El filtro de vegetación depende de que el producto incluya ese atributo.

## Integridad y significado de las fechas

Las fechas mínima y máxima de un archivo de detecciones **no prueban que todos los días y lugares fueran observados**. Por eso estos lotes tienen la base de disponibilidad `observed_dates_only`. El calendario muestra los conteos existentes y conserva el estado parcial o de integridad desconocida. No inventa ceros para áreas vacías ni porcentajes de cobertura del cielo.

El mapa global, el calendario y las exportaciones usan datos observados. El experimento de calibración sigue siendo peruano; no se aplica automáticamente a todos los países. La armonización científica y su validación mundial continúan pendientes.

## Ejecución reproducible

Desde la raíz, con el servidor separado de la base de preparación:

```powershell
.\mvp\.venv\Scripts\python.exe -u mvp/scripts/import_global.py --input data_abraham --data-dir data/world-build --start-year 2025 --end-year 2026
.\mvp\.venv\Scripts\python.exe -u mvp/scripts/verify_world.py --data-dir data/world-build --refresh-parquet
```

La primera orden conserva los lotes ya completados y reanuda por archivo. No ejecutar otra importación sobre la misma base ni activar esa base en el servidor mientras se está escribiendo desde la consola.

La verificación comprueba los hashes y el balance de filas de los nueve archivos mundiales, busca identidades duplicadas y contrasta consultas de julio de 2026 en Brasil, Australia, Indonesia, Estados Unidos y República Democrática del Congo. También verifica que los conteos del mapa coincidan con el análisis y que Parquet conserve todas las filas.

Los resultados cuantitativos se guardan localmente en `data/global-import.json` y `data/release-world-v0.3.json` al activar la base. Los datos y reportes generados permanecen fuera de Git; el código y estas instrucciones sí se versionan.
