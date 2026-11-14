# NINA 0.2 · Atlas mundial y laboratorio visual

[Arranque y uso](README.md). Esta entrega implementa la dirección visual acordada y amplía la adquisición al mundo. La versión anterior se conserva documentada en [ESTADO_V1.md](ESTADO_V1.md).

## Disponible

- Visor CesiumJS 3D/2D con imágenes reales NASA GIBS por teselas y caché local; referencia de imagen global disponible sin conexión. Sin cuenta Cesium ion ni servicio cartográfico de pago.
- Selección mundial, 177 geometrías de países Natural Earth, Perú y sus 26 divisiones, polígonos dibujados y coordenadas WGS84. Las geometrías mundiales tienen seis decimales y reparaciones topológicas identificadas; son cartografía generalizada de referencia.
- Territorio y período compartidos entre mapa, calendario, comparación y explicación; enlace reproducible de configuración.
- Comparador MODIS Aqua/VIIRS con divisiones reales de los marcadores, una cámara y controles accesibles. Forma cuadrada MODIS, circular VIIRS. No se mezclan sus conteos brutos.
- Calendario mensual, comparación descriptiva con la mediana elegible y perfil estacional; en móvil, años desplegables con meses legibles.
- Experimento interactivo sobre conteos peruanos reservados: estimación, referencia Aqua revelable, error absoluto y método. Separación temporal y reserva geográfica identificadas.
- Asistente contextual con hechos verificables, evidencias y orientación según rol. El motor local funciona; el proveedor LLM es opcional y no está configurado. La calibración del laboratorio sí utiliza un modelo de aprendizaje automático entrenado.
- Expedición guiada en tres pasos, expediente del análisis y cinco descargas reales: serie CSV, observaciones CSV, manifiesto JSON, informe TXT y figura SVG.
- Catálogo FIRMS consultado con MAP_KEY; instantánea mundial reciente y descarga de un mes por área en ventanas de hasta cinco días. Trabajos en segundo plano con progreso y persistencia.
- Importación global o por área; revisiones estándar/provisionales reconciliadas dentro de su ámbito, sin eliminar datos de otros territorios. Lecturas atómicas durante la ingesta local.

## Datos reales incorporados

| Conjunto | Ventana | Archivos | CSV, bytes | Filas nuevas |
|---|---|---:|---:|---:|
| Archivo peruano | 2000–2025 según producto | 48 | 163.067.831 | 2.034.899 |
| Mundo: MODIS, NOAA-20, NOAA-21 | 14-nov-2026, NRT | 3 | 4.116.918 | 49.410 |
| Rectángulo australiano: MODIS SP | Septiembre 2025 | 6 | 1.912.098 | 23.721 |
| Total incorporado | Ventanas identificadas | 57 | 169.096.847 | 2.108.030 |

La consulta exacta de Australia con la geometría Natural Earth contiene **12.934 detecciones Aqua** en septiembre de 2025. El total descargado del rectángulo también contiene Terra y puntos exteriores a esa geometría; se conservan y se filtran al analizar. La descarga se inició desde la interfaz y completó sus seis ventanas de cinco días.

## Verificación

- Compilación TypeScript/Vite de producción.
- 23 pruebas de backend: análisis, procedencia, revisiones, ámbitos, cobertura, importación y respuestas por rol. Fixtures aisladas de la base real.
- 20 comprobaciones automatizadas de navegador entre el recorrido principal y las interacciones adicionales, más una adquisición mensual real fuera de Perú. Incluyen cinco descargas, enlace restaurado, teclado, 2D/3D, formulario de área, expedición y móvil.
- Revisión visual de atlas, calendario, comparación, experimento, asistente y Australia. Capturas en `.nina-qa/nina-v2-*.png`.
- Verificación de SHA-256 de los archivos incorporados y correspondencia del snapshot Parquet mediante `scripts/verify_v2.py --refresh-parquet` con el servicio detenido; resultado en `data/release-v0.2.json`.

Las credenciales NASA permanecen exclusivamente en el backend y `.env`; no se incorporan al cliente, a los enlaces ni al manifiesto.

## Límites materiales

1. El histórico mundial completo no está descargado. La adquisición selectiva funciona y el calendario representa sus ventanas efectivas. La instantánea del día corriente es provisional y no equivale a un mes completo.
2. La armonización científica con oportunidades de observación, máscaras L2, exposición y geometría sigue pendiente. El modelo peruano es exploratorio y no se extrapola a otros países. No se fabrican porcentajes de cobertura ni intervalos.
3. Un conteo de píxeles no equivale a incendios individuales, área quemada, causa, pronóstico ni recomendación operativa.
4. El calendario usa UTC. Los países Natural Earth 110m y las divisiones geoBoundaries son geometrías de sus respectivos conjuntos, no una certificación de límites oficiales actuales.
5. Se mantiene un proceso local FastAPI/DuckDB y una cola de dos trabajadores. El almacenamiento particionado, servicios administrados y despliegue cloud son evolución de arquitectura, no infraestructura desplegada.
6. El globo requiere WebGL; el calendario y la consulta por coordenadas permanecen disponibles si el visor no inicia. Las teselas requieren conexión y la referencia de imagen local evita un fondo vacío.
7. Docker conserva su configuración, sin atribuir una prueba del motor o despliegue que no se haya realizado. La evaluación con stakeholders y la revisión científica independiente continúan pendientes.

## Siguiente trabajo científico

Obtener máscaras y geolocalización L2, reconstruir oportunidades y ceros válidos, evaluar sesgos e intervalos por dominio y publicar dónde la armonización tiene soporte. El diseño ya conecta selección, evidencia y abstención para incorporar ese resultado sin ocultar sus límites.
