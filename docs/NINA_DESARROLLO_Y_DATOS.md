# NINA 0.2: qué se desarrolló y cómo se procesan los datos

Las cifras de este documento corresponden a la entrega 0.2. La versión actual incorpora el archivo mundial: [estado 0.3](ESTADO_MUNDIAL.md) y [período y método de ingesta](ALCANCE_MUNDIAL.md).

Documento del estado implementado, revisado el **14 de noviembre de 2026** contra el código, los informes de verificación y la API local. Describe la aplicación que se abre en `http://127.0.0.1:8000`; el archivo `nina-demo.html` corresponde al prototipo anterior con datos simulados.

## 1. Respuesta directa: ¿son datos crudos o procesados?

**NINA muestra datos reales de NASA FIRMS que han pasado por procesamiento dentro de NINA.** No se limita a dibujar directamente la respuesta de una API. Descarga archivos, conserva sus originales, valida y normaliza registros, elimina duplicados técnicos, consulta una base local y calcula resultados por territorio y período.

Además, el CSV de FIRMS ya es un producto de detecciones generado a partir de observaciones satelitales. No es la señal cruda del sensor ni una imagen sin procesar. NASA utiliza las observaciones de MODIS y VIIRS para detectar fuegos activos y anomalías térmicas. [Descripción oficial de FIRMS](https://firms.modaps.eosdis.nasa.gov/).

Conviene distinguir cuatro niveles:

| Nivel | Qué contiene | Situación en NINA |
|---|---|---|
| Original recibido | CSV de FIRMS, anual o descargado mediante API | Conservado en `data/raw/`, con hash SHA-256 |
| Registro normalizado | Coordenadas, fecha, plataforma, FRP, confianza y procedencia en un esquema común | Almacenado en DuckDB; conserva el vínculo al archivo |
| Resultado analítico | Conteos mensuales, selección espacial, mediana histórica y diferencias descriptivas | Calculado por NINA a partir de registros observados |
| Estimación del modelo | Conteo mensual estimado en referencia a MODIS Aqua a partir de VIIRS | Experimental, limitado al caso peruano; separado de las detecciones |

**Procesar y organizar los datos no equivale a haber terminado la armonización científica entre MODIS y VIIRS.** La corrección por oportunidades de observación, nubes y geometría todavía está pendiente.

### Qué representa cada elemento visible

| Elemento | De dónde sale | Cómo interpretarlo |
|---|---|---|
| Puntos del atlas | Registros FIRMS normalizados y filtrados por el área, mes y sensor | Detecciones observadas; no puntos inventados por un modelo |
| Cantidad de detecciones | Conteo de todas las filas que cumplen la selección | No equivale a incendios individuales ni a superficie quemada |
| Calendario | Agregación mensual en UTC | Serie de detecciones del archivo incorporado |
| Mediana histórica | Mismo mes de hasta diez años anteriores elegibles | Referencia descriptiva de esa selección; requiere al menos cinco años |
| Diferencia porcentual | Comparación del mes contra su mediana | No es un pronóstico ni una medida de riesgo |
| Comparador MODIS/VIIRS | Dos consultas separadas con el mismo territorio y período | Permite observar diferencias entre instrumentos; no es una fusión armonizada |
| Estimación del laboratorio | Modelo entrenado con conteos peruanos | Resultado calculado, identificado como experimental |
| Referencia revelada en el laboratorio | Conteo Aqua reservado para la prueba | Observación real usada para evaluar el ajuste; no verdad completa del fuego existente |
| Fondo del globo | NASA GIBS, capa `BlueMarble_NextGeneration`, y referencia local | Imagen geográfica de referencia; **no cambia al mes seleccionado ni muestra incendios en vivo** |

## 2. Cómo se transforma un archivo de FIRMS

### Paso 1. Adquisición y conservación

Hay dos vías principales: archivos históricos anuales publicados por país y consultas FIRMS Area API. También se pueden importar CSV desde la interfaz.

La adquisición por API consulta primero la disponibilidad de cada producto. Una descarga mensual se divide en ventanas de hasta cinco días. Para un país o polígono, FIRMS recibe su rectángulo envolvente; el recorte exacto a la geometría seleccionada ocurre al analizar.

Cada archivo incorporado conserva su tamaño, hash, fuente, fechas, ámbito espacial y momento de importación. Una transferencia incompleta no se registra como una ventana disponible. La clave FIRMS se utiliza exclusivamente en el servidor y se omite de la procedencia exportada.

Código: [descarga histórica](../scripts/bootstrap_data.py), [adquisición API](../nina/remote.py), [ingesta](../nina/ingest.py).

### Paso 2. Validación y normalización

La ingesta comprueba coordenadas geográficas válidas, fecha/hora, plataforma y campos numéricos. Los registros rechazados se contabilizan, con ejemplos del motivo. La hora FIRMS se interpreta en UTC; en esta versión no hay agrupación por calendario civil de Lima.

Las denominaciones de fuentes se normalizan: por ejemplo, NOAA-20 se representa internamente como `viirs-jpss1`, y NOAA-21 como `viirs-jpss2`. MODIS conserva la separación entre Terra y Aqua.

La tabla analítica guarda 16 campos: identificador, fuente, plataforma, adquisición, latitud, longitud, FRP, confianza, versión, procesamiento, día/noche, tipo, división peruana, lote, scan y track. El archivo original conserva además las columnas de FIRMS que no entran en este esquema.

**FRP y confianza se conservan como atributos del producto. No se aplica una calibración física de FRP ni se convierte la confianza de MODIS y VIIRS a una probabilidad común.** Tampoco se ejecuta un nuevo detector de fuego sobre imágenes.

Código: `parse_row` en [nina/ingest.py](../nina/ingest.py).

### Paso 3. Duplicados y revisiones

La identidad técnica combina fuente, plataforma, fecha/hora y coordenadas expresadas a seis decimales. Esto permite evitar cargar dos veces el mismo registro al repetir importaciones.

No se agrupan detecciones cercanas para declarar que pertenecen al mismo incendio. Tampoco se elimina un punto VIIRS por estar cerca de otro MODIS: son observaciones distintas.

Se diferencian productos provisionales `NRT` y estándar `SP`. La ingesta da prioridad al estándar dentro de las ventanas espaciales y temporales correspondientes, para evitar sumar como nuevas observaciones las versiones provisionales reemplazadas. Esta reconciliación no es una armonización entre instrumentos.

Código: `ingest_file` en [nina/ingest.py](../nina/ingest.py).

### Paso 4. Asignación territorial y almacenamiento

Shapely asigna detecciones a las divisiones peruanas disponibles. Los archivos mundiales conservan registros de otros países aunque no tengan una división peruana asignada.

DuckDB es la base consultada por la aplicación. El archivo Parquet es una copia analítica que se actualiza explícitamente; no se regenera automáticamente con cada descarga desde la interfaz.

| Ubicación | Contenido |
|---|---|
| `data/raw/` | CSV originales descargados o importados |
| `data/nina.duckdb` | Observaciones, lotes, análisis y estados de trabajos |
| `data/processed/*.json` | Informes de ingesta por lote |
| `data/processed/observations.parquet` | Copia analítica comprimida |
| `data/models/benchmark.json` | Coeficientes, métricas e identificación de modelos |
| `data/catalog/` | Disponibilidad de productos consultada en FIRMS |
| `data/tiles/` | Caché local de imágenes del mapa |
| `data/boundaries/` y `web/public/assets/` | Geometrías e información de cartografía |

El histórico anual peruano conserva 5.452 detecciones sin asignación a su geometría administrativa; siguen en el total nacional. No se debe interpretar el total de registros mundiales sin departamento peruano como un error geográfico.

Código: [nina/store.py](../nina/store.py), [nina/ingest.py](../nina/ingest.py).

### Paso 5. Consulta y cálculo

Una selección especifica ámbito, geometría o división, fuente, plataforma, años, mes, día/noche y tipo de detección. Para polígonos se hace primero un filtro rectangular y después una comprobación exacta contra **la geometría de referencia seleccionada**; eso no certifica la precisión de los límites políticos reales.

Los conteos se calculan sobre todas las filas seleccionadas, antes del muestreo visual. La mediana usa el mismo mes de hasta diez años anteriores con archivo mensual elegible. Se requieren cinco valores como mínimo.

La diferencia descriptiva se calcula como `100 × (valor / mediana − 1)`. Se omite si el mes es parcial, no hay mediana suficiente o la mediana es cero.

Código: [nina/analytics.py](../nina/analytics.py).

### Paso 6. Presentación y exportación

El mapa normal entrega como máximo 10.000 puntos; el comparador, como máximo 8.000 por instrumento. Si hay más registros, el servidor selecciona una muestra determinista ordenada por identificador. Las respuestas distinguen `total` y `shown`.

**La muestra afecta los puntos dibujados, no el conteo mensual.** No es una muestra estadística diseñada para inferir densidad espacial: una zona visualmente vacía no prueba ausencia de detecciones en el conjunto completo.

El CSV de observaciones exporta todas las filas normalizadas del área y mes seleccionados, con sus filtros. Aunque la interfaz lo llame «Observaciones originales», **no es una copia byte a byte del CSV NASA**: esos originales están en `data/raw/`. La exportación tampoco incluye automáticamente otros meses o sensores fuera de la selección.

Código: `points_for_analysis` en [nina/analytics.py](../nina/analytics.py), exportaciones en [nina/main.py](../nina/main.py) y figura en [web/src/export.ts](../web/src/export.ts).

## 3. Qué significa «sin datos», «parcial» y «cero»

| Estado | Significado en esta implementación |
|---|---|
| No disponible | No hay una salida sustentada por las ventanas o registros incorporados para esa selección |
| Archivo parcial | Hay detecciones o una ventana de archivo, pero no soporte para considerar completo el mes |
| Archivo observado | Las ventanas registradas cubren el mes y el ámbito conforme a las reglas del sistema |
| Cero del archivo | El archivo mensual elegible no tiene detecciones que cumplan los filtros |

La elegibilidad se deriva de las fechas de los archivos anuales, las ventanas solicitadas a la API o, en una importación manual, las fechas declaradas por quien importa. **No mide cuánto territorio estuvo libre de nubes ni cuántas oportunidades válidas tuvo cada sensor.** Un cero del archivo no demuestra ausencia física de fuego.

Las fechas nacionales no se atribuyen automáticamente al mundo. Actualmente, un polígono personalizado dentro de Perú tampoco hereda automáticamente toda la disponibilidad anual nacional: puede quedar como parcial de manera conservadora.

Los campos de porcentaje de cobertura e intervalo permanecen sin valor cuando no se han calculado. No se rellenan con cifras de demostración.

## 4. Cuánta información real está incorporada

Corte de entrega 0.2 del 14 de noviembre de 2026. El total fue contrastado con `/api/status` al preparar este documento.

| Conjunto incorporado | Ventana | Archivos | Detecciones nuevas |
|---|---|---:|---:|
| Archivo peruano | 2000–2025, según producto | 48 | 2.034.899 |
| Instantánea mundial MODIS, NOAA-20 y NOAA-21 | 14 de noviembre de 2026, NRT | 3 | 49.410 |
| Rectángulo que contiene Australia, MODIS SP | Septiembre de 2025 | 6 | 23.721 |
| **Total** | **Ventanas identificadas, no historia mundial continua** | **57** | **2.108.030** |

Los CSV suman **169.096.847 bytes**, aproximadamente 169 MB decimales. La copia Parquet verificada contiene las mismas 2.108.030 filas y ocupa 67.353.689 bytes. Son tamaños de estos artefactos, no del proyecto completo.

Ejemplo concreto de procesamiento: se descargaron **23.721 registros MODIS** del rectángulo australiano. Al seleccionar el polígono de Australia y únicamente Aqua para septiembre de 2025, quedan **12.934 detecciones**. Los totales difieren por los filtros de plataforma y geometría; no porque el mapa invente o pierda registros.

El visor tiene alcance mundial y permite adquirir nuevos meses por área. **Todavía no contiene el histórico de todos los países.** La instantánea mundial de un día tampoco equivale a un mes completo.

Evidencia: [inventario de entrega](../data/release-v0.2.json), [estado de la versión](ESTADO_V2.md).

## 5. Qué aplicación se desarrolló

### Atlas y selección compartida

Se reemplazó el visor anterior por CesiumJS, con globo 3D, vista 2D y cartografía real. El usuario puede elegir el mundo, Perú, sus 26 divisiones de referencia, países, un polígono dibujado o un rectángulo por coordenadas WGS84. El catálogo mundial contiene 177 geometrías Natural Earth generalizadas.

La selección conecta mapa, calendario, comparación, explicación y exportación. Se puede compartir mediante una URL. Esa URL restaura la configuración, pero **no congela una copia histórica de la base**: los resultados pueden cambiar después de nuevas adquisiciones.

Se añadieron inspección de puntos, controles de cámara, adaptación móvil y alternativa informativa si WebGL no inicia. No se requiere Cesium ion. El fondo tiene una referencia local; las teselas que no estén en caché necesitan conexión.

Archivos: [App.tsx](../web/src/App.tsx), [Globe.tsx](../web/src/Globe.tsx), [style.css](../web/src/style.css).

### Calendario

La matriz de años y meses permite explorar la serie, seleccionar períodos y revisar su referencia histórica. El color usa una escala logarítmica indicada en la interfaz; los números conservan sus valores originales. En móvil se despliegan los meses de cada año.

Los períodos parciales y no disponibles tienen estados visibles. El perfil estacional acompaña el análisis y se puede descargar como SVG.

Archivo: [Calendar.tsx](../web/src/Calendar.tsx).

### Laboratorio visual y expedición

El comparador coloca MODIS Aqua y un VIIRS seleccionado en una misma escena, con cámara común y deslizador. MODIS utiliza cuadrados; VIIRS, círculos. El deslizador funciona con teclado.

La comparación comparte área y mes, **no garantiza pasadas simultáneas ni empareja píxeles de una misma observación**. Sus diferencias no pueden atribuirse directamente a cambios reales del fuego.

Debajo aparece el experimento de sustitución: una estimación, la referencia Aqua que se puede revelar y su error. Este experimento utiliza un caso peruano separado; no aplica el modelo automáticamente al país seleccionado en el globo.

La expedición guía una presentación en tres pasos: explorar el problema, comparar observadores y revelar la evidencia del experimento.

Archivos: [App.tsx](../web/src/App.tsx), [Experiment.tsx](../web/src/Experiment.tsx).

### Fuentes, evidencia y descargas

El panel Fuentes muestra el inventario, la disponibilidad FIRMS, los trabajos de adquisición y la importación de CSV. La descarga mensual muestra progreso y conserva las ventanas incorporadas.

Se implementaron cinco salidas: serie mensual CSV, detecciones CSV, manifiesto JSON, informe TXT y figura SVG. Los análisis identifican selección, revisión de datos y revisión del software. Si los datos o el código cambian, la API rechaza el uso de un análisis desactualizado para exportar o preguntar y pide regenerarlo.

El manifiesto incluye el catálogo de lotes incorporados. Es procedencia a nivel de archivo y revisión de base; no debe interpretarse como una lista mínima de todos y solo los archivos que aportaron filas al resultado.

Archivos: [DataPanel.tsx](../web/src/DataPanel.tsx), [Dialog.tsx](../web/src/Dialog.tsx), [nina/main.py](../nina/main.py).

## 6. Qué IA existe y qué hace

### Modelo estadístico entrenado

Se implementó una regresión Poisson regularizada que estima conteos mensuales en referencia a Aqua a partir del conteo VIIRS y de términos estacionales. Se compara contra un método más simple: multiplicar VIIRS por un factor aprendido del entrenamiento.

| Parte | Datos utilizados |
|---|---|
| Entrenamiento | 2018–2022, excluyendo las regiones reservadas |
| Selección de regularización | Año 2023, excluyendo las regiones reservadas |
| Prueba temporal | 2024–2025 |
| Comprobación geográfica adicional | Subconjunto de regiones reservado mediante una regla determinista |

Hay modelos guardados para VIIRS S-NPP y NOAA-20. No hay un modelo NOAA-21 entrenado en esta entrega.

| Instrumento de entrada | MAE del modelo | MAE del factor simple | Pares de prueba |
|---|---:|---:|---:|
| VIIRS S-NPP | 11,067 | 12,396 | 587 |
| VIIRS NOAA-20 | 10,907 | 12,709 | 597 |

MAE es el error absoluto medio en detecciones por región/mes frente al archivo Aqua. Un valor menor indica mejor ajuste en este conjunto de prueba; **no es un porcentaje de exactitud ni demuestra validez mundial**.

Hay una limitación metodológica relevante: el entrenamiento parte de meses con conteo VIIRS positivo. Si no aparece conteo Aqua en ese grupo, se utiliza cero de archivo; no se verifica que Aqua tuviera una oportunidad válida sin detección. El experimento visible, por su parte, solo muestra pares en los que aparecen ambos conteos. Su error por caso no tiene por qué coincidir con la métrica global del benchmark.

Faltan máscaras y geolocalización L2, oportunidades válidas, control de nubes y geometría e intervalos evaluados. El modelo no reconstruye todavía una serie de fuego libre de esos sesgos.

Código y resultados: [nina/science.py](../nina/science.py), [benchmark.json](../data/models/benchmark.json).

### Asistente contextual

El asistente actual usa **reglas y respuestas deterministas apoyadas en el análisis**. Puede explicar el período, las diferencias instrumentales, la disponibilidad y preparar un informe. Presenta los hechos que respaldan la respuesta y adapta la orientación a gestión territorial, investigación o comunicación.

Existe un adaptador opcional a un proveedor LLM, pero **no está configurado** al revisar esta entrega. Si se habilita, el diseño actual le permite aportar una frase de orientación; las cifras continúan saliendo del servidor. No es un agente que ejecute consultas geoespaciales libres ni un sistema RAG documental completo.

Código: [nina/assistant.py](../nina/assistant.py), [Dialog.tsx](../web/src/Dialog.tsx).

## 7. Arquitectura realmente implementada

| Componente | Tecnología | Responsabilidad |
|---|---|---|
| Interfaz | React, TypeScript y Vite | Selección, navegación, calendario, paneles y exportación SVG |
| Visualización espacial | CesiumJS | Globo, 2D, puntos, geometrías y comparación |
| API | FastAPI y Uvicorn | Análisis, adquisiciones, evidencia, exportaciones y asistente |
| Base analítica | DuckDB | Consultas de observaciones y persistencia local |
| Procesamiento espacial | Shapely | Validación, asignación territorial y recorte por geometría |
| Cálculo del modelo | NumPy y SciPy | Ajuste Poisson y evaluación contra el método simple |
| Adquisición | HTTPX y almacén de confianza del sistema | Acceso a FIRMS y NASA GIBS |
| Trabajos | Dos trabajadores dentro del proceso Python | Descarga, importación y entrenamiento en segundo plano |
| Archivos | Disco local, CSV, JSON y Parquet | Originales, procedencia, modelo y copia analítica |

El navegador consulta la API local; la API consulta DuckDB y accede a NASA cuando se solicita una adquisición o una tesela no guardada. No se llama a FIRMS para recalcular cada clic del calendario sobre datos ya incorporados.

La base protege lecturas y escrituras con un bloqueo del proceso para evitar mezclar revisiones durante análisis y exportaciones. Esta solución requiere **un solo proceso de servidor** para el uso local actual. Los estados de trabajos se guardan; al reiniciar, un trabajo pendiente se marca interrumpido y debe volver a ejecutarse. No hay una cola distribuida con reanudación automática.

No están desplegados PostgreSQL/PostGIS, almacenamiento S3, colas administradas, autenticación multiusuario ni infraestructura cloud. Docker tiene configuración, pero no se atribuye una ejecución del motor que no se haya verificado.

### Rutas principales

| Ruta | Función |
|---|---|
| `GET /api/health` | Versión y presencia de configuraciones, sin revelar claves |
| `GET /api/status` | Inventario y observaciones incorporadas |
| `GET /api/catalog` | Disponibilidad consultada a FIRMS |
| `GET /api/places` y `/api/regions` | Geometrías de referencia |
| `POST /api/analyses` | Calcular y registrar un análisis |
| `GET /api/analyses/{id}/points` | Puntos observados y metadatos de muestreo |
| `GET /api/analyses/{id}/comparison` | Dos instrumentos para la misma selección |
| `GET /api/analyses/{id}/evidence` | Selección, revisiones y procedencia |
| `GET /api/analyses/{id}/exports/{kind}` | Serie, observaciones, manifiesto o informe |
| `POST /api/acquisitions` y `/api/acquisitions/month` | Incorporar ventanas recientes o un mes |
| `POST /api/import` | Importar un CSV FIRMS con su ámbito |
| `GET /api/jobs` | Consultar estado de trabajos |
| `GET /api/experiments/substitution` | Obtener pares reservados y estimaciones |
| `GET /api/models` y `POST /api/models/train` | Consultar o entrenar el modelo exploratorio |
| `POST /api/assistant` | Explicar un análisis existente |

El contrato vivo se puede consultar en `http://127.0.0.1:8000/docs` y `http://127.0.0.1:8000/openapi.json`.

## 8. Qué se verificó

La entrega 0.2 registra las siguientes comprobaciones; no se volvieron a ejecutar todas para este cambio exclusivamente documental:

- Compilación de producción TypeScript/Vite.
- 23 pruebas de backend sobre análisis, importación, ámbitos, revisiones, disponibilidad, procedencia y asistente.
- 20 comprobaciones automatizadas de navegador: navegación, comparación, teclado, móvil, experimento, enlace compartido y cinco descargas, entre otras.
- Descarga mensual real iniciada desde la interfaz para Australia, septiembre de 2025, completada en seis ventanas.
- Verificación de hashes de los 57 archivos y correspondencia de filas del Parquet con la base.
- Revisión visual de las vistas principales y de la presentación móvil.

Al preparar este documento se revisaron nuevamente el código, los informes de entrega y las respuestas locales de `/api/health` y `/api/status`: versión `0.2.0`, 2.108.030 observaciones y LLM externo sin configurar.

Referencias: [pruebas de backend](../tests/test_nina.py), [estado de entrega](ESTADO_V2.md), [informe de datos](../data/release-v0.2.json). Los informes y capturas del navegador están en `.nina-qa/`, un directorio local excluido del control de versiones.

Estas comprobaciones verifican funcionamiento del software y trazabilidad. No sustituyen una validación científica independiente ni pruebas con usuarios reales.

## 9. Qué falta para completar la propuesta científica

| Trabajo pendiente | Por qué hace falta |
|---|---|
| Descargar y alinear productos L2 de máscaras y geolocalización | Saber dónde y cuándo hubo oportunidad de observar |
| Reconstruir oportunidades y ausencias válidas | Separar falta de observación de ausencia de detección |
| Diseñar y evaluar la armonización por dominio | Estimar diferencias instrumentales con controles apropiados |
| Evaluar incertidumbre y transferencia geográfica | Publicar dónde funciona el método y dónde debe abstenerse |
| Ampliar casos históricos fuera de Perú | Evaluar generalización; el visor global no la demuestra por sí solo |
| Evaluar tareas con stakeholders | Comprobar comprensión y utilidad para decisiones reales |
| Preparar despliegue y operación multiusuario | Hacer que la solución local pueda operar como un servicio compartido |

El siguiente paso científico es construir el soporte de observación y evaluar el método sobre él. Agregar más puntos al globo, por sí solo, no resuelve esa necesidad.

## 10. Cómo revisar la entrega

Abrir `http://127.0.0.1:8000`. Si el servidor está detenido, desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn nina.main:app --host 127.0.0.1 --port 8000
```

Un recorrido concreto para comprobar el trabajo:

1. Elegir **Perú**, **MODIS Aqua**, **septiembre de 2025** y revisar atlas y calendario.
2. Abrir **Laboratorio** y desplazar el comparador; observar que las fuentes conservan conteos separados.
3. Revisar el experimento peruano, revelar Aqua y consultar el error y el método.
4. Abrir la explicación y contrastar sus cifras con los hechos mostrados.
5. Exportar observaciones y manifiesto para revisar registros y procedencia.
6. Seleccionar **Australia**, **MODIS Aqua**, **septiembre de 2025**: el conjunto incorporado contiene 12.934 detecciones para esa geometría.

Más información: [arranque y uso](../README.md), [fuentes](DATA_SOURCES.md), [estado 0.2](ESTADO_V2.md) y [dirección de producto](../design/NINA-direccion-de-producto.md).

Este documento utiliza tablas y una secuencia de pasos. No incluye diagramas porque Excalidraw MCP no estaba disponible en la sesión de elaboración.
