# NINA — Plan de implementación y evolución mundial

**Dirección vigente 0.2:** [estado actual](ESTADO_V2.md). Implementados: rediseño del atlas con CesiumJS, vista 2D, contexto compartido, comparación de observadores, experimento reservado, calendario móvil, evidencia contextual, enlaces compartibles y adquisición por área/mes. Se verificaron una instantánea mundial y un mes australiano, además del archivo peruano. La armonización con oportunidades válidas, la validación científica global y el despliegue administrado siguen pendientes. Las secciones nacionales siguientes documentan la primera fase y no limitan el alcance vigente.

Actualizado el 13 de noviembre de 2026. Este es el documento principal para seguir el trabajo. La [arquitectura](NINA-arquitectura.md) explica las decisiones técnicas y el [catálogo de fuentes](DATA_SOURCES.md) documenta los datos. Las fechas de desarrollo no restringen el alcance de este plan.

**Actualización de implementación:** ya existe la aplicación local 0.1 con histórico real nacional. Consultar [README.md](../README.md) para arrancarla y [ESTADO_V1.md](ESTADO_V1.md) para el estado de cada tarea. La aplicación de observación y los modelos exploratorios están disponibles; la armonización con oportunidades válidas y la validación con usuarios permanecen pendientes.

## 1. Alcance recomendado de la primera entrega

**Primera fase ya entregada: todo el Perú.** La versión 0.2 amplía la selección y adquisición al mundo, conservando este conjunto como caso histórico y de validación. El estado efectivo de cobertura se publica por ventana y ámbito.

La recomendación nacional permite evaluar un producto concreto con usuarios, contrastar costa, sierra y selva, y controlar el procesamiento. No procede de una demostración de que el alcance mundial sea técnicamente imposible. El ejemplo de 68 TB mencionado en la conversación corresponde a un millón de archivos de geolocalización de 68,2 MB; no es un cálculo del almacenamiento requerido por NINA ni por el historial de puntos de FIRMS.

El alcance peruano incluye:

- Histórico de detecciones disponible desde comienzos de los 2000 y actualización reciente.
- Calendario, comparación del mismo mes con su historia, cobertura y límites de interpretación.
- Observaciones originales y conteos equivalentes claramente identificados.
- Laboratorio de sustitución de sensor con resultados medidos fuera del entrenamiento.
- Descarga de datos, gráficos, metodología y procedencia.
- Asistente que responda sobre el análisis seleccionado y prepare informes con evidencia.

El HTML actual tiene tres áreas esquemáticas y datos simulados. No representa todavía esta cobertura nacional conectada. Las primeras pruebas técnicas usarán períodos pequeños para comprobar lectura y acceso; eso no cambia el alcance geográfico del producto. Madre de Dios puede ser un caso de demostración entre otros, no el límite del proyecto.

## 2. Cuánta información necesitamos

### A. Inventario completo de focos para Perú

Objetivo: obtener todas las detecciones disponibles para el territorio en las fuentes seleccionadas, conservando plataforma, colección y revisión. El archivo de puntos FIRMS publica estos comienzos; la disponibilidad efectiva estándar y reciente se comprobará por fuente.

| Fuente | Período objetivo | Propósito |
|---|---|---|
| MODIS Terra y Aqua, C6.1 | Desde 1-nov-2000 hasta la última fecha disponible | Histórico; separar Terra/Aqua y validar el puente inicial |
| VIIRS S-NPP | 20-ene-2012 a 2-nov-2026, según disponibilidad del archivo | Solapamiento histórico y continuidad entre instrumentos |
| VIIRS NOAA-20 | Desde 1-abr-2018 hasta la última fecha disponible | Solapamiento y observaciones recientes |
| VIIRS NOAA-21 | Desde 1-mar-2023 hasta la última fecha disponible | Continuidad reciente y evaluación de otra plataforma |

Fuente de períodos y mecanismos: [archivo FIRMS](https://firms.modaps.eosdis.nasa.gov/download/). El archivo documenta CSV, SHP y JSON y autenticación mediante Earthdata o código por email. El importador inicial usará CSV. El sufijo estándar no garantiza por sí solo que el último día esté disponible.

El historial se descargará por lotes de archivo/período, con reanudación y control de integridad. La API servirá para consultas acotadas y actualizaciones. No hace falta cargar todo el país y todos los años simultáneamente en memoria.

### B. Máscaras, geolocalización y oportunidades de observación

Para la metodología propuesta necesitamos productos L2 MODIS/VIIRS y sus dependencias, en los períodos y pasadas relevantes que intersecten Perú. Estos archivos pueden contener una franja mayor que el país: filtrar el catálogo por Perú no garantiza una reducción del tamaño proporcional a su superficie.

Se seleccionarán por huella y tiempo, se procesarán por lotes y se construirán tablas compactas de oportunidades de observación. Las máscaras permiten distinguir observaciones válidas sin detección de lugares sin observación válida. Si una entrada científica necesaria no está disponible, el resultado debe conservar ese estado.

La descarga inicial para comprobar formatos y el muestreo de entrenamiento son menores que el procesamiento final. **No se presentará como calendario nacional armonizado una salida que solo tenga soporte científico en unos pocos ejemplos.** El despliegue nacional mostrará explícitamente dónde el método está validado y dónde la estimación no se puede emitir.

### C. Datos complementarios

Un límite nacional y divisiones administrativas con procedencia y condiciones de uso adecuadas, más auxiliares justificados por la evaluación. Cobertura del suelo, ecorregiones y área quemada son candidatos, no descargas obligatorias completas del planeta. Para el territorio peruano se declarará la zona civil `America/Lima` y se conservará también UTC.

### Volumen: lo conocido y lo pendiente

**El archivo nacional de puntos ya está medido:** 163.067.831 bytes de CSV, más la base y Parquet documentados en el manifiesto de entrega. Todavía no se han sumado exhaustivamente los gránulos L2 y sus dependencias; el total del proyecto científico sigue sin un dimensionamiento completo. No se confunde el volumen medido de CSV con el almacenamiento de toda la solución.

Ejemplos de escala, exclusivamente ilustrativos:

- Diez millones de filas de 100 bytes por fila ocuparían aproximadamente **1 GB** de CSV. Esto no afirma que Perú tenga diez millones de filas ni que ese sea el tamaño de sus registros.
- Mil archivos de 68,2 MB ocuparían aproximadamente **68,2 GB**; un millón, **68,2 TB**. NASA publica 68,2 MB como tamaño de referencia para [VNP03MODLL](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp03modll-002). No se ha verificado que cada archivo real tenga ese tamaño.

Se medirán por separado:

| Magnitud | Cómo se determina |
|---|---|
| Bytes de descarga | Suma de tamaños del inventario, separando datos publicados y tamaños desconocidos |
| Almacenamiento permanente | Originales retenidos, tablas normalizadas, oportunidades, resultados y versiones |
| Espacio temporal máximo | Mayor lote simultáneo, archivos descomprimidos y resultados intermedios |
| Memoria de procesamiento | Medición sobre un lote real representativo; no igual al tamaño del archivo completo |
| Coste operativo | Recursos medidos y tarifas del entorno elegido, después del inventario |

Las políticas de retención se fijan con ese inventario. Los datos usados en el benchmark y sus manifiestos se conservarán para reproducción. Cuando un archivo auxiliar solo se mantenga en caché, se registrarán identificador/versionado, checksum y procedencia; reproducirlo después dependerá de conservarlo o poder recuperarlo de la fuente.

## 3. Arquitectura definida

```text
FIRMS + productos L2 que intersectan Perú
                    ↓
Ingestión y controles de calidad — Python
                    ↓
Objetos originales + GeoParquet + catálogo PostgreSQL/PostGIS
                    ↓
Oportunidades válidas → armonización → evaluación reservada
                    ↓
Calendario y evidencia — FastAPI + DuckDB
                    ↓
Web — React/TypeScript + MapLibre + gráficos SVG
                    ↓
Asistente con herramientas e informes con referencias
```

El procesamiento científico se ejecuta en un worker, separado de las peticiones web. Las consultas utilizan agregados y particiones por plataforma, período y ubicación. La primera organización del código será un repositorio con módulos de datos, ciencia, API y web.

El despliegue de referencia sigue siendo contenedores, almacenamiento de objetos, PostgreSQL y cola de trabajos; AWS es la ruta descrita en la arquitectura. El tamaño y coste se determinarán con mediciones. Desarrollo local y despliegue usarán los mismos contratos de datos.

La ampliación a otro país exigirá nuevos datos y evaluación del método; parametrizar el país evita acoplar el software a Perú, pero no demuestra que un modelo peruano generalice a todo el mundo.

## 4. Orden del trabajo y entregables

Los pasos siguientes se ordenan por dependencia, sin asignar fechas arbitrarias.

| Paso | Resultado que debe quedar listo | Qué permite hacer |
|---|---|---|
| 1. Preparación | Geometría nacional, contrato de datos, accesos probados e inventario con tamaños | Saber qué se descargará y dónde procesarlo |
| 2. Detecciones nacionales | Histórico bruto por fuente con controles, revisiones y manifiestos | Consultar y exportar observaciones reales de todo el Perú |
| 3. Observación y ciencia | Oportunidades válidas, pares, baseline y modelo evaluados | Estimar una serie comparable y conocer sus límites |
| 4. Producto conectado | API, mapa nacional, calendario, comparación y exportación | Explorar el país y áreas particulares con datos reales |
| 5. Asistente útil | Consultas e informes por rol con cifras verificadas | Interpretar el análisis y preparar comunicaciones |
| 6. Cierre de la entrega | Reproducción, revisión con usuarios y demo científica | Defender resultados, utilidad y limitaciones |

La API y la interfaz pueden avanzar con contratos y fixtures mientras se procesan los datos. Las cifras científicas y las respuestas de IA se conectan únicamente cuando existen resultados identificados y verificables.

## 5. Tareas ejecutables

**Estado al crear este plan:** arquitectura documentada, catálogo revisado y demo simulada disponibles. El [estado actualizado de las tareas tras implementar 0.1](ESTADO_V1.md) distingue lo ejecutado de lo pendiente; la tabla siguiente conserva dependencias y criterios de terminación. E1 = responsable de datos/ciencia; E2 = responsable de producto/plataforma. El reparto es propuesto para los dos ingenieros.

| ID | Tarea | Depende de | Responsable | Criterio de terminación |
|---|---|---|---|---|
| N01 | Preparar repositorio, entorno y módulos | — | E2 | Entorno reproducible; comandos de ejecución documentados |
| N02 | Fijar geometrías y contrato de observación/análisis | — | Ambos | AOI nacional y divisiones con procedencia; UTC, unidades, estados y versiones definidos |
| N03 | Probar accesos e inventariar fuentes por período y huella | N02 | E1 | Consulta FIRMS y lectura L2 verificadas; inventario con tamaños conocidos/desconocidos y mecanismo de descarga |
| N04 | Medir un lote y dimensionar almacenamiento/procesamiento | N03 | Ambos | Bytes, tiempo, memoria, espacio temporal y política de retención medidos; decisión local/cloud documentada |
| N05 | Implementar descarga reanudable del histórico nacional | N01, N03, N04 | E1 | Todas las particiones solicitadas tienen estado, checksum y revisión; fallos y ausencias visibles |
| N06 | Normalizar y controlar la calidad de detecciones | N02, N05 | E1 | GeoParquet por fuente/período, deduplicación técnica, informe de calidad y conteos reconciliados con originales |
| N07 | Construir oportunidades de observación y emparejamientos | N03, N04, N06 | E1 | Máscaras alineadas; detecciones, ceros válidos y desconocidos separados; reglas temporales/espaciales versionadas |
| N08 | Fijar particiones y benchmark nacional | N06, N07 | Ambos | Regiones y años reservados; costa/sierra/selva y tipos de cobertura pertinentes; prevención de fuga |
| N09 | Ajustar baseline y modelo candidato | N08 | E1 | Comparación fuera de muestra de error, sesgo, incertidumbre y extremos; elección justificada |
| N10 | Evaluar puentes Terra–Aqua y entre plataformas VIIRS | N08, N09 | E1 | Alcance temporal/geográfico y fallos publicados; períodos sin soporte identificados |
| N11 | Producir calendario y evidencia versionados | N09, N10 | E1 | Agregación nacional y por AOI; mediana comparable, mes parcial y estados de soporte correctos |
| N12 | Implementar API de consulta y trabajos | N01, N02 | E2 | Contratos, filtros, estados, caché por revisión y manejo de errores; conexión científica requiere N11 |
| N13 | Implementar mapa y selección nacional | N02, N12 | E2 | Todo el Perú, divisiones y polígonos; carga por escala y navegación accesible |
| N14 | Conectar calendario, laboratorio y exportaciones | N11, N12, N13 | E2 | Una selección comparte cifras y procedencia en interfaz, CSV, gráficos y manifiesto |
| N15 | Integrar herramientas y redacción del asistente | N11, N12 | E2 | Consultas por rol, referencias a análisis y verificación de cifras; alternativa por plantillas |
| N16 | Evaluar asistente y tareas con usuarios | N14, N15 | Ambos | Casos de insuficiencia, cambios de AOI y premisas falsas; comprensión y correcciones documentadas |
| N17 | Incorporar actualización reciente y revisión NRT→SP | N05, N06, N11 | E1 | Reingestión idempotente; revisión sin doble conteo; fecha de adquisición y actualización visibles |
| N18 | Desplegar, comprobar reproducción y preparar presentación | N14, N16, N17 | Ambos | Ejecución reproducida, producto accesible y demostración con resultados reales y un caso de abstención |

Un hito funcional temprano termina con N06, N12 y N13: se pueden consultar detecciones reales nacionales. La versión científica requiere además N07–N11. La IA explicativa depende de esa evidencia; no determina los valores del calendario.

## 6. Qué hacemos inmediatamente

El bloque inicial de entorno, archivo público, descarga y aplicación local ya se ejecutó en 0.1. La siguiente dependencia científica es **N07**: obtener y alinear máscaras/geolocalización para construir oportunidades válidas, junto con el dimensionamiento L2 y las comprobaciones de acceso restantes de N03–N04. El detalle vigente está en [ESTADO_V1.md](ESTADO_V1.md).

**Actualización 0.1:** se descargaron los 48 archivos públicos anuales de Perú, se importaron 2.034.899 detecciones y se ajustaron calibraciones exploratorias con prueba reservada. No se ha contratado infraestructura cloud ni validado aún el modelo con máscaras y oportunidades L2. «Cobertura nacional» significa que el producto admite todo el territorio y comunica los huecos reales; no que fabrique observaciones donde los satélites no aportan soporte.

## 7. Documentos de referencia

- [DATA_SOURCES.md](DATA_SOURCES.md): fuentes, variantes, fechas, límites de API y verificación pendiente.
- [NINA-arquitectura.md](NINA-arquitectura.md): método científico, componentes y contrato del asistente.
- [nina-demo.html](../nina-demo.html): referencia visual de la experiencia; datos simulados.
- [Enunciado del reto](exa-results/nasa-space-apps-2026-2026-11-12/enunciado-a.txt): solicitud de calendario, selección de región y descargas. El texto facilitado admite áreas de interés y no exige cobertura mundial.
