# NINA 0.1 · Estado real de la entrega

Registro de la entrega original. Para el estado vigente y la ampliación mundial consultar [ESTADO_V2.md](ESTADO_V2.md).

Fecha local de entrega: 13-nov-2026. [Instrucciones de uso](README.md).

## Disponible y verificado

- Aplicación React/TypeScript con API FastAPI y base DuckDB local.
- 48 archivos NASA FIRMS nacionales descargados, con 163.067.831 bytes de CSV y hashes SHA-256.
- 2.034.899 detecciones únicas de MODIS, S-NPP y NOAA-20, entre 2000 y 2025.
- Clasificación por la geometría geoBoundaries incorporada; se preservan las detecciones nacionales sin asignación a una división del conjunto.
- Mapa real con selección nacional, divisiones y polígonos, calendario, filtros y comparación descriptiva.
- Exportaciones CSV/JSON/TXT/SVG vinculadas al análisis y a la revisión del archivo.
- Dos calibraciones exploratorias Poisson, comparadas con un factor simple en datos reservados.
- Asistente determinista con evidencia y adaptador opcional LLM que conserva los números calculados por el servidor.
- Importación de CSV, trabajos persistidos y cliente de actualización reciente activable con MAP_KEY.
- Scripts de instalación, carga reanudable y arranque; archivos de contenedor preparados.
- Compilación de producción correcta, 13 pruebas de backend y 13 comprobaciones automatizadas en Chrome, con revisión visual de escritorio y móvil.

Las pruebas del backend usan fixtures en directorios separados. Los escenarios sintéticos no se importaron en la base real.

## Límites materiales

1. **La armonización científica final sigue pendiente.** No se han descargado/alineado máscaras L2 ni construido oportunidades de observación. El laboratorio es un baseline exploratorio, no una serie corregida por cobertura.
2. No hay datos NOAA-21 ni de 2026 en el índice anual descargado. La interfaz los representa como no disponibles y admite nuevos CSV o consultas recientes con credenciales.
3. Las credenciales NASA y del proveedor de lenguaje no estaban configuradas al entregar. La conexión autenticada y el proveedor LLM real no se probaron; el asistente local sí se probó.
4. La geometría de 2008 del conjunto usado contiene 26 divisiones, no es una certificación administrativa oficial actual. 5.452 detecciones se conservan sin departamento asignado.
5. El calendario se agrupa en UTC. Las comparaciones de conteos son descriptivas; no se declara significancia, predicción de incendios ni atribución causal.
6. El servicio local usa un solo proceso y DuckDB. PostgreSQL, almacenamiento S3, cola administrada y despliegue AWS siguen como arquitectura de evolución. Docker está preparado, sin atribuirle una ejecución que no se haya comprobado.
7. La revisión científica independiente y la validación con stakeholders siguen pendientes; una prueba automatizada no las sustituye.

## Relación con el plan

Los estados siguientes evitan interpretar «versión 0.1 funcional» como todas las fases científicas y de despliegue completadas.

| Tarea | Estado de esta entrega |
|---|---|
| N01 · Entorno y módulos | Implementados; dependencias fijadas y comandos documentados |
| N02 · Geometría y contrato | Implementación nacional con geometría versionada; actualización oficial de límites pendiente |
| N03 · Accesos e inventario | Índice público y descarga CSV verificados; metadatos L2 muestreados, acceso científico autenticado pendiente |
| N04 · Dimensionamiento | Medidos CSV, base y Parquet; presupuesto completo L2 pendiente |
| N05 · Descarga nacional | Completa para los 48 archivos publicados en el índice consultado; ampliación reciente/NOAA-21 pendiente de otra fuente |
| N06 · Normalización | Implementada y ejecutada; una detección duplicada técnica y cero filas rechazadas en el archivo inicial |
| N07 · Oportunidades válidas | Pendiente de máscaras y geolocalización alineadas |
| N08 · Benchmark | Implementado para conteos mensuales exploratorios; benchmark de oportunidades pendiente |
| N09 · Modelos | Baseline de escala y candidato Poisson calculados; validez científica de la armonización pendiente |
| N10 · Puentes de sensores | No validados todavía; no se completan artificialmente los períodos sin soporte |
| N11 · Calendario científico | Calendario observado y calibración exploratoria disponibles; serie con exposición corregida pendiente |
| N12 · API | Implementada y probada localmente |
| N13 · Mapa nacional | Implementado y comprobado en navegador |
| N14 · Exportaciones | Implementadas y comprobadas con cinco descargas reales |
| N15 · Asistente | Motor local probado; adaptador LLM preparado, conexión real pendiente de configuración |
| N16 · Evaluación | Pruebas de software completadas; evaluación con usuarios pendiente |
| N17 · Actualización | Cliente y tratamiento estándar/provisional implementados y probados con fixtures; llamada autenticada real pendiente |
| N18 · Despliegue y entrega | Aplicación local compilada y ejecutada; despliegue cloud y presentación científica final pendientes |

## Siguiente fase científica

Configurar accesos, obtener una muestra L2 y su geolocalización, verificar máscaras/dimensiones y construir oportunidades sobre soporte común. Solo después se podrá entrenar y evaluar la armonización que controla la observación y ampliar su alcance validado. El software de esta entrega ya permite consultar, inspeccionar y exportar los datos necesarios para estudiar ese siguiente paso.
