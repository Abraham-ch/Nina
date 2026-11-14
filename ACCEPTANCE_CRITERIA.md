# Criterios de aceptación · Procesamiento y armonización de focos de calor

> Ubicación en el repo: `packages/harmonization/ACCEPTANCE_CRITERIA.md`
> Aplica a todo cambio en `packages/harmonization/` y `pipelines/`.
> Complementa a `AGENTS.md` (§5–§10). Si hay conflicto, **este archivo prevalece** para el procesamiento de datos.

## Cómo usar este documento (instrucciones para el agente)

1. Antes de empezar, identifica qué criterios toca tu tarea (columna **Área**).
2. Un criterio **[OBL]** (obligatorio) no puede quedar sin cumplir. Uno **[REC]** (recomendado) puede
   postergarse, pero debes dejarlo anotado en el reporte como `pendiente` y explicar el motivo.
3. Cada criterio indica **cómo se verifica**: un test automatizado, un artefacto generado o una revisión.
   Si el test no existe, créalo; no marques el criterio como cumplido sin evidencia.
4. Al terminar, genera `data/reports/acceptance_<run_id>.md` con la plantilla del final, indicando para cada
   criterio afectado si está `cumple`, `no cumple`, `no aplica` o `pendiente`, junto con su evidencia.
5. Formato de los criterios: **Dado** (contexto) · **Cuando** (acción) · **Entonces** (resultado esperado).

### Fuentes citadas

| Clave | Documento |
|---|---|
| **GUÍA** | *MODIS C6/C6.1 Active Fire Product User's Guide* v1.0 (Giglio et al.) |
| **README** | `Readme.txt` incluido en las descargas de NASA FIRMS |
| **C61** | *MODIS C61 Land – Proposed Changes* |
| **AGENTS** | `AGENTS.md` de este repositorio |

---

## 1. Ingesta y origen de los datos (ING)

**ING-01 [OBL] · Identificación del origen por nombre de archivo**
- Dado un ZIP o archivo de FIRMS con prefijo `DL_FIRE_M-C61`, `DL_FIRE_SV-C2`, `DL_FIRE_J1V-C2` o `DL_FIRE_J2V-C2`,
- cuando se ingiere,
- entonces cada fila recibe `instrument`, `satellite_norm` y `source_file` coherentes con el prefijo, y
  los archivos `DL_FIRE_LS_*` (Landsat) se excluyen con `qa_reason = "excluded_instrument"`.
- *Verificación:* `test_ingest_detects_source_from_filename` con un archivo por prefijo.
- *Fuente:* README.

**ING-02 [OBL] · Calidad estándar vs. NRT**
- Dado un archivo `fire_archive_*` o `fire_nrt_*`,
- cuando se ingiere,
- entonces `quality_level` es `standard` o `nrt` según el nombre. Si el nombre no lo indica, se usa el campo
  `version` (si contiene `NRT`, es `nrt`).
- *Verificación:* test parametrizado con ambos tipos de archivo y con versiones `"6.1NRT"`, `"61.03"`, `"2.0NRT"`, `"2"`.
- *Fuente:* README.

**ING-03 [OBL] · Precedencia de los datos estándar sobre los NRT**
- Dado que existen datos estándar y NRT para el mismo `satellite_norm` y la misma `acq_date_utc`,
- cuando se consolida,
- entonces se conservan solo los estándar y los NRT se registran con `qa_reason = "superseded_by_standard"`.
- *Verificación:* `test_standard_supersedes_nrt`; el reporte de QA muestra el conteo.
- *Fuente:* README (los NRT se reemplazan aprox. 3 meses después).

**ING-04 [OBL] · Calidad de NOAA-20 y NOAA-21 según lo que exista**
- Dados datos de NOAA-20 o NOAA-21,
- cuando se ingieren,
- entonces `quality_level` se determina por la fuente real (`VIIRS_NOAA20_SP` → `standard`; `*_NRT` → `nrt`) y **no** por una
  regla fija. Qué sensores tienen datos estándar, y hasta qué fecha, se consulta en `/api/data_availability` (ING-09).
  NOAA-21 sigue siendo solo NRT hasta que esa consulta diga lo contrario.
- *Verificación:* test con respuestas simuladas de `data_availability`.
- *Fuente:* README (dice que no hay datos estándar de NOAA-20/21; **está desactualizado**: la API ya ofrece `VIIRS_NOAA20_SP`).

**ING-05 [OBL] · Descargas vacías**
- Dado un CSV que solo tiene cabecera, un DBF vacío o un JSON `[]`,
- cuando se ingiere,
- entonces el proceso termina sin error, registra `0 filas` para ese archivo y continúa.
- *Verificación:* `test_empty_inputs` con los tres casos.
- *Fuente:* README.

**ING-06 [OBL] · Codificación y proyección**
- Dado cualquier archivo de entrada,
- cuando se lee,
- entonces se lee en UTF-8 (tolerando BOM), las coordenadas se tratan como EPSG:4326 y no se intenta interpretar
  `Readme.txt` (trae caracteres mal codificados).
- *Verificación:* test con un fixture que tenga BOM; revisión del código.
- *Fuente:* README.

**ING-07 [OBL] · Datos de referencia globales para detectar huecos**
- Dado que se procesa una región de interés,
- cuando se calculan la cobertura y los huecos (GAP-02),
- entonces se usan **conteos diarios globales (o de una zona amplia) por satélite**, no solo los de la región.
  Fuente sugerida: archivos mensuales MCD14ML (SFTP de la Universidad de Maryland) o descarga global de FIRMS.
- *Verificación:* existe `data/interim/global_daily_counts.parquet` con las columnas `satellite_norm`, `date`, `n`.
- *Fuente:* GUÍA §7.1.1 (los archivos de focos no informan de datos faltantes) y §4.3.

---

## 2. Esquema y tipos (SCH)

**SCH-01 [OBL] · Contrato de entrada JSON**
- Dado un `.json` cuya raíz es un array de objetos,
- cuando se valida contra `hotspot_input.schema.json`,
- entonces se aceptan los campos de AGENTS §6 y se rechazan con `schema_invalid` las filas a las que les falte
  algún campo requerido.
- *Verificación:* `test_schema_valid_modis_example` (objeto de ejemplo de `data_type`) y `test_schema_invalid_rows`.
- *Fuente:* AGENTS §6.

**SCH-02 [OBL] · Campos numéricos que llegan como texto**
- Dados `confidence: "48"`, `type: "0"` y `acq_time: "0000"`,
- cuando se normalizan,
- entonces se obtiene `confidence_raw = "48"` y la clase `nominal`, `hotspot_type = 0` y la hora `00:00 UTC`.
  Además, `acq_time` dado como `"618"` o `618` se interpreta como `06:18 UTC`.
- *Verificación:* test parametrizado.
- *Fuente:* AGENTS §6.1, GUÍA §5.5 (Tabla 10: `HHMM` en UTC).

**SCH-03 [OBL] · Colección y versión**
- Dado un registro MODIS con `version` de la Colección 6 o 6.1 (`"6.0"`, `"6.1"`, `"61.03"`, `"6.1NRT"`, etc.),
- cuando se normaliza,
- entonces se acepta **sin aplicar ningún ajuste** entre C6 y C6.1. Un registro de una colección anterior (que empiece
  por `5` o `4`) se rechaza con `qa_reason = "unsupported_collection"`.
- *Verificación:* test parametrizado de versiones.
- *Fuente:* GUÍA §2.1 (C6 y C6.1 pueden mezclarse; FRP sin cambios; diferencia global del 0,001 %), C61 (los cambios de
  calibración afectan las bandas 1 y 2, no las térmicas), GUÍA §7.3 (los problemas de C5 no deben entrar).

**SCH-04 [OBL] · Campos de brillo por instrumento**
- Dado un registro MODIS (`brightness`, `bright_t31`) o VIIRS (`bright_ti4`, `bright_ti5`, o sus alias `brightness` y `brightness_2`),
- cuando se normaliza,
- entonces se mapean a `bt_mir_k` y `bt_tir_k` sin perder el valor original.
- *Verificación:* test con un fixture de cada instrumento.
- *Fuente:* AGENTS §7.1.

---

## 3. Dominio temporal (TMP)

**TMP-01 [OBL] · Fecha de inicio de la serie**
- Dado un registro MODIS con `acq_datetime_utc < 2000-11-01`,
- cuando se valida,
- entonces se rechaza con `qa_reason = "pre_nov2000_quality"`.
- *Verificación:* `test_rejects_pre_november_2000`.
- *Fuente:* GUÍA §7.2.1 (antes de nov-2000 hubo detectores dañados, bandeado, fuegos no detectados y, en feb–mar 2000,
  líneas de barrido completas marcadas como fuego) y GUÍA §8.3.10.

**TMP-02 [OBL] · Tiempo en UTC**
- Dado cualquier registro,
- cuando se almacena,
- entonces `acq_datetime_utc` está en UTC. La conversión a hora local solo ocurre en la API o la UI.
- *Verificación:* test y revisión del esquema (`timestamptz`).
- *Fuente:* GUÍA §5.5 (Tabla 10), AGENTS §8.

**TMP-03 [OBL] · Cobertura calculada a partir de los datos**
- Dada una corrida del pipeline,
- cuando termina,
- entonces la tabla `coverage` tiene `first_date` y `last_date` reales por `satellite_norm` y `quality_level`.
  No se aceptan fechas fijas escritas en el código.
- *Verificación:* artefacto `coverage` + test.
- *Fuente:* AGENTS §5.3.

**TMP-04 [OBL] · Climatología con años completos**
- Dado el cálculo de la climatología mensual,
- cuando se definen los años de referencia,
- entonces se usa por defecto **2001 → último año completo**. Se excluyen 2000 (incompleto, y antes de nov-2000 no es fiable)
  y los meses que no cumplan GAP-04.
- *Verificación:* test sobre la función de climatología.
- *Fuente:* GUÍA §7.2.1, AGENTS §8.

---

## 4. Huecos y cobertura de observación (GAP)

**GAP-01 [OBL] · Catálogo de huecos conocidos**
- Dado `packages/harmonization/known_gaps.yaml`,
- cuando se revisa,
- entonces contiene **como mínimo** estos periodos, cada uno con su fuente:

  | Satélite | Periodo | Fuente |
  |---|---|---|
  | Terra | antes del 2000-11-01 (problemas de hardware y calibración) | GUÍA §7.2.1 |
  | Terra | septiembre de 2000 (instrumento inoperativo) | GUÍA §8.3.3 |
  | MODIS | finales de junio a inicios de julio de 2001 | README |
  | MODIS | 2002, faltantes intermitentes | README |
  | MODIS | desde mediados de agosto de 2007 | README |
  | MODIS | 21-abr-2009 (parcial) y 22-abr-2009 (completo) | README |
  | **Aqua** | **16-ago-2020 → 02-sep-2020** (falla del FMU; cobertura limitada a recepción directa) | GUÍA §7.2.4 |

- *Verificación:* test que carga el YAML y comprueba que estos periodos estén presentes.

**GAP-02 [OBL] · Detección automática de huecos**
- Dados los conteos diarios globales (ING-07),
- cuando un satélite tiene 0 detecciones globales en un día, o un conteo por debajo del 10 % de la mediana móvil de 31 días,
- entonces ese día se registra en `data_gaps` con `reason = "detected_outage"`, aunque no figure en GAP-01.
- *Verificación:* `test_detects_outage` con una serie sintética que tenga un apagón.
- *Fuente:* GUÍA §7.1.1 y §8.3.3, README.

**GAP-03 [OBL] · Un hueco no es un cero**
- Dado un día o mes de una región sin observación válida,
- cuando se generan los agregados (`harmonized_cell_day`, calendario),
- entonces el valor es `data_gap = true` con el conteo en `null`, **nunca** `0`.
- *Verificación:* `test_gap_is_not_zero` con el periodo de Aqua de 2020 y con 22-abr-2009.
- *Fuente:* GUÍA §7.1.1 (que falte un foco no implica que no hubo fuego).

**GAP-04 [OBL] · Cobertura parcial de MODIS (Terra o Aqua ausente)**
- Dado un día en que solo uno de los dos satélites, Terra o Aqua, tiene datos,
- cuando se agrega MODIS combinado,
- entonces el día se marca `partial_coverage = true`. Un mes con más del 20 % de días con hueco o cobertura parcial se
  excluye de la calibración (HAR) y de la climatología (TMP-04) y se muestra en la UI como "cobertura incompleta".
- *Verificación:* test con agosto de 2020 (Aqua ausente, Terra presente).
- *Fuente:* GUÍA §7.2.4.

**GAP-06 [OBL] · Huecos oficiales de FIRMS**
- Dado el servicio `missing_data` de FIRMS (DATA_SOURCES §1.2),
- cuando se actualiza `data_gaps`,
- entonces se incorporan las fechas que FIRMS publica como faltantes (estándar y NRT, por satélite) con `reason = "firms_missing_data"`.
  Esto complementa GAP-01 y GAP-02, no los reemplaza.
- *Verificación:* test con una respuesta simulada; el reporte de QA cuenta los huecos por origen.

**GAP-07 [OBL] · Fin de misión no es un hueco**
- Dado un satélite que terminó su misión (S-NPP desde el 2026-11-02 13:00 UTC, y Terra o Aqua cuando corresponda),
- cuando no hay detecciones posteriores a esa fecha,
- entonces la tabla `coverage` registra `end_of_mission` y esos días **no** se marcan como `detected_outage` ni `data_gap`.
  La fecha se configura en `sensor_lifecycle.yaml`, nunca en el código.
- *Verificación:* `test_end_of_mission_not_gap` con S-NPP en noviembre de 2026.
- *Fuente:* aviso de NASA/NESDIS sobre el fin de S-NPP.

**GAP-05 [REC] · Nubosidad y observabilidad**
- Dados los productos mensuales en grilla de MODIS (MOD14CMQ/MYD14CMQ, 0,25°), con las capas `MeanCloudFraction`, `TotalPix` y `CloudCorrFirePix`,
- cuando se integran,
- entonces cada celda-mes con `MeanCloudFraction > 0.6` (configurable) se marca `low_observability`, y la relación
  `CloudCorrFirePix / RawFirePix` se guarda como indicador de cuánto podrían estar subestimados los conteos.
- *Verificación:* artefacto `cloud_observability.parquet` y test de lectura.
- *Fuente:* GUÍA §3.6, §5.4.2 y §7.1.1.

---

## 5. Confianza de la detección (CONF)

**CONF-01 [OBL] · Umbrales de MODIS**
- Dado un valor de confianza MODIS `C`,
- cuando se clasifica,
- entonces es `low` si `0 ≤ C < 30`, `nominal` si `30 ≤ C < 80` y `high` si `80 ≤ C ≤ 100`. Un valor fuera de 0–100
  o que no sea numérico se registra como `schema_invalid`.
- *Verificación:* test con los valores límite `29, 30, 79, 80, 100, 101, "abc"`.
- *Fuente:* GUÍA §8.4.3 (Tabla 11).

**CONF-02 [OBL] · Clases de VIIRS**
- Dados `l`, `n` y `h`, entonces se clasifican como `low`, `nominal` y `high`. Cualquier otro valor es `schema_invalid`.
- *Verificación:* test.

**CONF-03 [OBL] · Filtro por defecto**
- Dada la configuración por defecto,
- cuando se filtra,
- entonces se conservan solo las detecciones `nominal` y `high`; las `low` se registran como `low_confidence`.
  El umbral se puede cambiar con `MIN_CONFIDENCE_CLASS`.
- *Verificación:* test y conteo de `low_confidence` en el reporte de QA.
- *Fuente:* GUÍA §5.1.3 y §8.4.2 (para reducir las falsas alarmas se recomienda usar solo nominal y alta).

**CONF-04 [OBL] · La confianza no se usa como peso**
- Dada cualquier agregación o calibración,
- entonces la confianza solo se usa como **filtro**, nunca como ponderación.
- *Verificación:* revisión de código.
- *Fuente:* GUÍA §7.2.2 (algunos píxeles dudosos siguen clasificados como nominales), AGENTS §9.2.

---

## 6. Tipo de foco y fuentes estáticas (TYPE)

**TYPE-01 [OBL] · Filtro por `type` en los datos estándar**
- Dado un registro con el campo `type`,
- cuando se filtra,
- entonces solo se conserva `type = 0` (presunto incendio de vegetación). `1` (volcán activo), `2` (otra fuente terrestre
  estática) y `3` (mar adentro) se registran como `non_vegetation_type`.
- *Verificación:* test parametrizado.
- *Fuente:* GUÍA §5.5 (Tabla 10).

**TYPE-02 [OBL] · Máscara de fuentes estáticas con el criterio de la guía**
- Dados los focos de VIIRS y los NRT, que no traen `type`, y también los MODIS estándar,
- cuando se construye `static_source_mask`,
- entonces una celda de ~1 km (H3 res. 8, configurable) se marca como estática si tuvo detecciones en **16 días o más
  de un mismo año calendario**, o si está en **zona urbana**, o a menos de 2 km (configurable) de un **volcán activo**,
  o sobre **agua** (posible quema de gas en el mar).
- *Verificación:* test con una serie sintética de 16 y de 15 días; artefacto `static_source_mask.parquet`.
- *Fuente:* GUÍA §5.5 (definición de `type = 2`: 16 días o más en un año calendario, más zonas urbanas según MCD12Q1; los
  `type` 0–2 son solo de tierra y el 3 corresponde a agua).

**TYPE-03 [OBL] · La máscara también se aplica a los MODIS con `type = 0`**
- Dado un foco MODIS estándar con `type = 0` que cae en una celda de `static_source_mask`,
- cuando se filtra,
- entonces se excluye con `qa_reason = "static_source_mask"`, y el reporte de QA muestra cuántos `type = 0` capturó la máscara.
- *Verificación:* test y conteo en el reporte.
- *Fuente:* GUÍA §7.2.3 (algunas fuentes estáticas no están marcadas en `type`).

**TYPE-04 [OBL] · Validación de la máscara frente a MODIS `type = 2`**
- Dado el periodo de solapamiento con datos MODIS estándar,
- cuando se compara la máscara construida con datos VIIRS contra las celdas MODIS con `type ∈ {1, 2}`,
- entonces la máscara recupera **al menos el 80 %** de esas celdas y elimina **como máximo el 2 %** de las detecciones
  MODIS `type = 0` (umbrales configurables y documentados).
- *Verificación:* artefacto `data/reports/static_mask_validation_<version>.json`; el flujo falla si no se cumplen los umbrales.
- *Fuente:* GUÍA §5.5 y §7.2.3.

**TYPE-05 [OBL] · Datos auxiliares de la máscara**
- Dada la máscara,
- entonces usa: zonas urbanas de **MCD12Q1** (clase IGBP 13, "Urban and Built-up"), con GHSL como alternativa;
  volcanes del **Smithsonian GVP**; y una máscara de tierra/agua. Cada fuente queda registrada en `data/sources.yaml` (ver AUX-01).
- *Verificación:* revisión de `sources.yaml` y test de carga.
- *Fuente:* GUÍA §5.5 y C61 (MCD12Q1 C6.1 trae una corrección menor en la clase UMD; usar la versión C6.1).

---

## 7. Geometría del píxel (PIX)

**PIX-01 [OBL] · Área del píxel**
- Dados `scan` y `track` (en km),
- cuando se normaliza,
- entonces se calcula `pixel_area_km2 = scan × track` y se conserva.
- *Verificación:* test (para el ejemplo de `data_type`: 2,5 × 1,5 = 3,75 km²).
- *Fuente:* GUÍA §8.4.6 (el píxel MODIS mide nominalmente 1 km² y crece lejos del nadir).

**PIX-02 [OBL] · El conteo de celdas no depende del tamaño del píxel**
- Dados dos focos del mismo satélite y la misma pasada que caen en la misma celda H3 de agregación,
- cuando se calcula `active` (AGENTS §10.1),
- entonces la celda cuenta **una sola vez**.
- *Verificación:* `test_cell_counts_once`.
- *Fuente:* GUÍA §7.1.1 (riesgo de mal uso de las ubicaciones de píxel).

**PIX-03 [REC] · Sensibilidad al ángulo de barrido**
- Dado el periodo de solapamiento,
- cuando se valida la armonización,
- entonces el reporte incluye una comparación de resultados con y sin los focos de `pixel_area_km2 > 4` (configurable).
- *Verificación:* sección presente en `validation_<version>.json`.
- *Fuente:* GUÍA §8.4.6.

---

## 8. Resolución temporal y sesgo de muestreo (SAMP)

**SAMP-01 [OBL] · Unidad principal del calendario**
- Dados los agregados para la app,
- cuando se generan los productos del calendario,
- entonces la unidad principal es **mensual**, y las anomalías y rankings solo se calculan con agregaciones de **8 días o más**.
- *Verificación:* test sobre la función de anomalías: `freq="day"` debe lanzar `ValueError` o devolver la advertencia `sampling_bias`.
- *Fuente:* GUÍA §7.1.1 (sesgos graves en intervalos menores de unos 8 días) y §8.6.2.

**SAMP-02 [OBL] · Advertencia en las salidas diarias**
- Dada una salida diaria (serie o CSV agregado),
- entonces incluye `sampling_bias_warning = true` en sus metadatos y la API la propaga hacia la UI.
- *Verificación:* test de contrato de `/timeseries?freq=day`.
- *Fuente:* GUÍA §7.1.1.

**SAMP-03 [OBL] · Combinación de Terra y Aqua**
- Dados Terra y Aqua,
- cuando se agrega MODIS,
- entonces ambos se combinan en una sola serie MODIS (como el producto MCD14ML, que reúne los dos). Aqua no existe antes de
  julio de 2002, y la calibración debe considerar ese cambio en la frecuencia de muestreo: estrato `modis_terra_only`
  antes de jul-2002 y `modis_terra_aqua` desde entonces.
- *Verificación:* test y coeficientes de calibración separados.
- *Fuente:* GUÍA §3.7 y §8.6.2 (con un solo instrumento el muestreo es insuficiente en periodos cortos).

---

## 9. Armonización MODIS ↔ VIIRS (HAR)

**HAR-01 [OBL] · Estratificación**
- Dado el ajuste de calibración,
- entonces se estima por **bioma o ecorregión** (p. ej., RESOLVE Ecoregions 2017) **× mes calendario** y **× estrato de muestreo**
  (SAMP-03). Si un estrato tiene menos de 30 celdas-mes con actividad, se usa el estrato superior (bioma → región → global).
- *Verificación:* artefacto `calibration_<version>.parquet` con las columnas `stratum`, `month`, `sampling_stratum`, `n`, `coef`, `fallback_level`.

**HAR-02 [OBL] · Periodo de calibración**
- Dado el periodo de solapamiento,
- entonces la calibración MODIS ↔ VIIRS usa **solo datos estándar** de MODIS y de VIIRS S-NPP, desde el 2012-01-20 hasta la última
  fecha estándar de S-NPP (como mucho el 2026-11-02), excluyendo los NRT, NOAA-21 y los meses afectados por GAP-03, GAP-04 o TYPE.
  NOAA-20 estándar solo se usa para el puente entre sensores VIIRS (SRC-02).
- *Verificación:* aserción en el flujo y test.
- *Fuente:* README, GUÍA §7.2.4, aviso de fin de S-NPP (DATA_SOURCES §1.1).

**HAR-03 [OBL] · Validación cruzada dejando años fuera**
- Dada una calibración,
- cuando se valida dejando un año fuera cada vez,
- entonces |sesgo relativo| ≤ 10 % y Spearman de la estacionalidad mensual ≥ 0,8 en al menos el 80 % de los estratos con datos.
  Si no se cumple, **no se publica** el dataset.
- *Verificación:* `validation_<version>.json`; el flujo devuelve un código de error.
- *Fuente:* AGENTS §10.3.

**HAR-04 [OBL] · Sin saltos en 2012**
- Dada la serie armonizada de una región de prueba,
- cuando se compara MODIS calibrado ("equivalente VIIRS") con VIIRS observado en 2012–2014,
- entonces la diferencia mensual media es ≤ 10 %.
- *Verificación:* test de integración con un fixture regional.

**HAR-05 [OBL] · Reproducibilidad**
- Dadas las mismas entradas y la misma configuración,
- cuando se ejecuta el pipeline dos veces,
- entonces el hash de `harmonized_cell_day` es idéntico.
- *Verificación:* test de reproducibilidad (semillas fijas, orden determinista).

**HAR-06 [REC] · Validación externa**
- Dada el área quemada **MCD64A1**,
- entonces el reporte incluye la correlación mensual entre la actividad armonizada y el área quemada por estrato.
- *Fuente:* GUÍA §8.3.9 (no hay una relación constante entre píxel y área quemada: se usa solo como validación, no como conversión).

---

## 10. QA, salidas y trazabilidad (OUT)

**OUT-01 [OBL] · Ninguna fila se pierde sin registro**
- Dada una corrida,
- entonces `filas_leídas = filas_aceptadas + Σ filas_rechazadas(qa_reason)` por archivo.
- *Verificación:* test de cuadre sobre el reporte de QA.
- *Fuente:* AGENTS §2.3.

**OUT-02 [OBL] · Reporte de QA**
- Dada una corrida,
- entonces `data/reports/qa_<run_id>.json` contiene: filas por archivo, rechazos por `qa_reason`, cobertura por satélite,
  días con hueco (conocidos y detectados), días sospechosos, `type = 0` capturados por la máscara y el porcentaje de `low_confidence`.
- *Verificación:* validación del JSON contra `qa_report.schema.json`.

**OUT-03 [OBL] · Umbral de errores de esquema**
- Si `schema_invalid / filas_leídas > 1 %` en cualquier archivo, entonces el flujo falla.
- *Verificación:* test.

**OUT-04 [OBL] · Versión del dataset**
- Dado un dataset publicado,
- entonces `dataset_versions` registra `harmonization_version`, la fecha, el hash de la configuración, las métricas de HAR-03 y TYPE-04,
  y las versiones de cada dato auxiliar.
- *Verificación:* consulta a la tabla y test.

**OUT-05 [OBL] · Cita y aviso legal**
- Dado cualquier artefacto exportable,
- entonces va acompañado de la cita de FIRMS, los **DOI de los productos usados** (DATA_SOURCES §1.6) y el aviso de que los datos
  no son aptos para decisiones tácticas o a escala local.
- *Verificación:* test de exportación.
- *Fuente:* README.

---

## 11. Datos auxiliares (AUX)

**AUX-01 [OBL] · Registro de fuentes**
- Dado `data/sources.yaml`,
- entonces cada fuente tiene: `name`, `url`, `version`/`collection`, `license`, `download_date`, `sha256` y `used_in` (criterios que la usan).
  Las URLs salen de `docs/DATA_SOURCES.md`, y toda URL marcada ⚠️ se verifica con una petición real antes de usarla.

**AUX-02 [OBL] · Licencias compatibles con el uso**
- Dado un dato auxiliar con licencia restrictiva (p. ej., **GADM: gratis solo para uso académico y no comercial**),
- cuando la app se vaya a publicar o a usar comercialmente,
- entonces se documenta la decisión en un ADR, o se reemplaza por una fuente con licencia abierta.
- *Verificación:* el campo `license` está en `sources.yaml` y existe el ADR correspondiente.

**AUX-03 [OBL] · Cautela con MCD12Q1 desde 2021**
- Dada la máscara urbana basada en MCD12Q1 v6.1,
- cuando se usan años de 2021 en adelante,
- entonces se usa el último año anterior a 2021 o se reemplaza por GHSL, y la elección queda registrada en `sources.yaml`.
- *Verificación:* revisión de la configuración y test de carga.
- *Fuente:* metadatos de MCD12Q1 v6.1 (los datos de entrenamiento no se actualizaron; el productor pide cautela desde 2021).

| Dato | Obligatorio | Usado en |
|---|---|---|
| FIRMS MODIS C6.1 estándar + NRT | Sí | todo |
| FIRMS VIIRS S-NPP estándar (2012-01-20 → 2026-11-02) | Sí | HAR, TYPE-04, SRC-02 |
| FIRMS VIIRS NOAA-20 estándar + NRT (2018 →) y NOAA-21 NRT (2024 →) | Sí | SRC-01, SRC-02, NRT |
| FIRMS `data_availability` y `missing_data` | Sí | ING-09, GAP-06 |
| Conteos diarios globales por satélite (MCD14ML mensual o FIRMS global) | Sí | ING-07, GAP-02 |
| Límites administrativos (GADM / INEI) | Sí | API, HAR-01 (respaldo) |
| Biomas o ecorregiones (RESOLVE 2017) | Sí | HAR-01 |
| MCD12Q1 C6.1 (clase urbana) o GHSL | Sí | TYPE-02, TYPE-05 |
| Volcanes Holoceno (Smithsonian GVP) | Sí | TYPE-02 |
| Máscara de tierra/agua | Sí | TYPE-02 |
| MOD14CMQ / MYD14CMQ (0,25°, mensual) | No | GAP-05 |
| MCD64A1 (área quemada) | No | HAR-06 |
| Zonas horarias IANA (timezone-boundary-builder) | No | fecha local en la API |

---

## 12. Continuidad de sensores y adquisición (SRC)

**SRC-01 [OBL] · Serie VIIRS sin S-NPP desde el 2-nov-2026**
- Dado que S-NPP dejó de entregar datos nuevos el **2026-11-02 a las 13:00 UTC**,
- cuando se construye la serie VIIRS posterior a esa fecha,
- entonces se usan NOAA-20 (y NOAA-21 como respaldo de continuidad). El job NRT **no** consulta `VIIRS_SNPP_NRT`, y una
  configuración que lo incluya falla al validarse.
- *Verificación:* test de la configuración del job NRT; aserción en `nrt_daily_flow`.
- *Fuente:* aviso de NASA FIRMS y NESDIS sobre el fin de S-NPP.

**SRC-02 [OBL] · Puente entre sensores VIIRS (S-NPP → NOAA-20)**
- Dado el solapamiento de datos **estándar** de S-NPP y NOAA-20 (2018 → 2026-11-02),
- cuando se arma la serie "equivalente VIIRS",
- entonces se estima un factor S-NPP ↔ NOAA-20 por estrato y mes (mismo método que HAR-01 y HAR-03) y se aplica a NOAA-20 desde el
  2026-11-02, para que el cambio de satélite no produzca un salto. Se valida con |sesgo relativo| ≤ 5 % en el solapamiento.
- *Verificación:* `inter_viirs_bridge_<version>.json` + test de continuidad en noviembre de 2026.
- *Fuente:* NASA indica que NOAA-20 y NOAA-21 llevan el mismo VIIRS en el mismo plano orbital, con unos 50 minutos de diferencia.
  La hora de paso distinta justifica comprobar el sesgo en vez de suponerlo nulo.

**SRC-03 [OBL] · MODIS sin final fijo**
- Dado que NASA recomienda migrar desde MODIS y que Terra es el único paso de la mañana,
- cuando Terra o Aqua dejen de entregar datos,
- entonces el pipeline sigue funcionando: la serie armonizada está anclada en VIIRS (MODIS solo se usa calibrado para
  2000–2011), se aplica GAP-07 y se registra el fin en `sensor_lifecycle.yaml`.
- *Verificación:* test simulando el fin de Terra y luego el de Aqua; la serie 2012 → hoy no cambia.

**SRC-04 [OBL] · Límites de la API de FIRMS**
- Dado el cliente de la API (`harmonization/io/firms_api.py`),
- entonces respeta **5000 transacciones cada 10 minutos por MAP_KEY** (contando cada día de `DAY_RANGE` como una transacción),
  usa `FIRMS_MAX_DAY_RANGE` (configurable, por defecto 5), reintenta con espera exponencial ante errores 429 y 5xx, y registra el consumo
  consultando el estado de la MAP_KEY.
- *Verificación:* test con un servidor simulado que devuelve 429; el número de transacciones calculado coincide con el registrado.

**SRC-05 [OBL] · Datos RT y URT**
- Dado que FIRMS elimina las detecciones RT y URT cuando procesa los NRT correspondientes, o pasadas 6 h,
- cuando corre el job NRT,
- entonces solo se ingieren como definitivos los NRT con más de 6 h de antigüedad. Las detecciones RT y URT, si se usan, se guardan como
  `quality_level = "rt"`, se marcan `is_provisional` y se reemplazan en la corrida siguiente.
- *Verificación:* test de reemplazo de RT por NRT.

**SRC-06 [OBL] · Disponibilidad y retraso del estándar**
- Dado `/api/data_availability`,
- cuando se decide qué periodo es provisional y qué reprocesar,
- entonces `is_provisional` se calcula a partir de la última fecha estándar real de cada sensor, no con un número de días fijo. FIRMS
  indica un retraso de unos 3 meses (Readme) o unos 5 meses (página de descarga), así que `PROVISIONAL_DAYS` solo sirve de respaldo
  (por defecto 150). Un job semanal reemplaza NRT por estándar cuando aparece.
- *Verificación:* test con fechas de disponibilidad simuladas.

**SRC-07 [OBL] · Credenciales**
- Dados `FIRMS_MAP_KEY` y Earthdata Login,
- entonces se leen de variables de entorno o de `~/.netrc`, nunca aparecen en logs, reportes ni commits, y el CI usa *secrets*.
- *Verificación:* test que busca patrones de clave (32 caracteres hexadecimales) en los logs; *secret scanning* en el CI.

**ING-08 [OBL] · Estrategia de adquisición documentada**
- Dado el pipeline,
- entonces el histórico se carga desde la herramienta de descarga del archivo o los resúmenes por país, lo reciente desde la API, y los
  archivos NRT sin clave solo como respaldo, según la tabla de DATA_SOURCES §3. No se usa la API para descargar años completos día a día
  si existe la descarga del archivo.
- *Verificación:* revisión de `pipelines/` y reporte de transacciones de la corrida.

**ING-09 [OBL] · Sensores y fechas tomados de la API**
- Dado el inicio de cada corrida,
- entonces el pipeline consulta `data_availability` y guarda la respuesta en `data/interim/data_availability_<run_id>.csv`. La
  cobertura (TMP-03), la calidad estándar o NRT (ING-04) y el reprocesamiento (SRC-06) se basan en ese archivo.
- *Verificación:* el archivo existe y el reporte lo referencia.

---

## Plantilla del reporte de aceptación

`data/reports/acceptance_<run_id>.md`

```markdown
# Reporte de aceptación · run <run_id> · harmonization <version>

| ID | Estado | Evidencia | Notas |
|---|---|---|---|
| ING-01 | cumple | tests/test_ingest.py::test_ingest_detects_source_from_filename | |
| GAP-01 | cumple | known_gaps.yaml (commit abc123) | |
| GAP-05 | pendiente | — | Falta descargar MOD14CMQ 2001–2024 |
| TYPE-04 | no cumple | static_mask_validation_0.3.0.json | recall 0.74 < 0.80 → ajustar radio de volcanes |
| ... | | | |

Resultado: ✅ apto para publicar / ❌ no apto (lista de criterios [OBL] incumplidos)
```

**Regla final:** el agente **no puede** publicar un dataset ni marcar la tarea como terminada si queda algún criterio
**[OBL]** en `no cumple` o sin evidencia.
