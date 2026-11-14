# NINA: dirección de producto y diseño

Exploración previa a la implementación. El resultado actual, los datos incorporados y lo que permanece pendiente se documentan en [ESTADO_V2.md](../ESTADO_V2.md).

Propuesta para discusión. No sustituye la versión 0.1 ni representa una armonización mundial implementada. Los tres conceptos visuales usan cartografía mundial de referencia y una muestra real fija de 200 observaciones de Perú de septiembre de 2025.

## Alcance correcto

El enunciado entregado describe un problema planetario y exige un calendario armonizado para un área de interés y un rango temporal seleccionados. No contiene una exigencia literal de procesar todos los países. Se recomienda un producto global porque amplía su utilidad y encaja con el problema, con evidencia de validación publicada por territorio, período y combinación instrumental.

Una Tierra navegable no equivale a tener armonización validada mundialmente. Perú conserva valor como conjunto de desarrollo y caso de validación. No se debe extrapolar la precisión del modelo exploratorio peruano al resto del planeta.

## Promesa y recorrido

**NINA permite investigar si cambió la actividad del fuego o cambió nuestra forma de observarla.**

Recorrido principal: localizar un territorio → seleccionar período → reconocer su temporada habitual → examinar una diferencia → comprobar observaciones y soporte → compartir o exportar evidencia.

Territorio y período persisten al cambiar de vista. El mapa, el calendario, la comparación y la explicación son partes de la misma investigación. El estado se conserva en un enlace reproducible.

## Tres direcciones compatibles

### Atlas inmersivo

El planeta ocupa la mayor parte de la pantalla, con imágenes reales y una selección temporal visible. A escala mundial se muestran agregados; al acercarse aparecen observaciones y geometrías pertinentes. Buscar un lugar o introducir coordenadas ofrece una alternativa a navegar con gestos. El globo no gira automáticamente durante el trabajo.

El 3D sirve para orientarse entre continentes y escalas. El análisis detallado conserva una vista 2D y evita alturas decorativas que puedan confundirse con intensidad, riesgo o magnitudes físicas.

### Laboratorio visual

Dos observadores comparten cámara y período, con comparación por deslizador y vista paralela accesible. La lectura bruta y la armonizada se identifican por separado. Las diferencias en resolución y horario no se presentan como un antes/después del mismo incendio.

La interacción distintiva sería una prueba de sustitución: reservar un sensor en un período de solapamiento, estimar el objetivo con el otro y revelar la referencia reservada. Mostrar error, sesgo, soporte y casos de abstención. El experimento debe diseñarse y validarse antes de mostrar conclusiones.

### Expedición guiada

Un recorrido opcional para presentar al jurado: una discontinuidad real del registro, su relación con el observador, el procedimiento de armonización y el resultado con sus límites. Cada escena abre el mismo análisis en la aplicación. El usuario puede omitirlo y explorar libremente.

## Ideas con valor funcional

1. **Firma estacional del territorio.** Calendario año × mes conectado al mapa, perfil mensual y mediana histórica comparable. El color distingue actividad; los valores y etiquetas permiten leerla sin depender del color.
2. **Lente de observabilidad.** Separar ausencia de detección de ausencia de observación válida. La cobertura se calcula con los productos científicos apropiados; un mapa de nubes decorativo no la reemplaza.
3. **Archivo instrumental visible.** Una banda temporal muestra qué plataformas aportaron datos, cambios de versión y períodos parciales. La serie armonizada mantiene accesibles sus observaciones originales.
4. **Prueba de sustitución del sensor.** La interacción descrita en el laboratorio explica y demuestra la contribución científica central.
5. **Comparar temporadas entre territorios.** Cada lugar se compara primero con su propio historial. No ordenar regiones de tamaños distintos por conteos brutos como si representaran el mismo riesgo.
6. **Pasada explicada en 3D.** Una escena breve ayuda a entender huella, resolución y horarios. Si no usa efemérides verificadas, se rotula como esquema conceptual.
7. **IA sobre la selección.** Preguntas como «¿qué cambió en este período?» o «¿es comparable con su historia?» llaman herramientas acotadas sobre el análisis. Cada cifra abre su fuente y cada interpretación conserva sus límites. Un informe adaptado al gestor o al científico aporta más que un chat permanente.
8. **Historia compartible.** Enlace con AOI, período, versión y configuración; descarga del calendario, las observaciones y el manifiesto de procedencia. La narración nunca sustituye los datos.

## Criterio visual

- Jerarquía territorial: mapa protagonista, controles compactos y un solo detalle contextual a la vez.
- Tipografía editorial para títulos y una familia legible para análisis; cifras alineadas cuando se comparan.
- Azul profundo como fondo cartográfico; tonos neutros en superficies de lectura; color reservado para sensores, actividad y selección con correspondencia estable.
- Imágenes reales con atribución. Un mapa de referencia compuesto no se presenta como imagen adquirida en la fecha seleccionada.
- Transiciones que conservan la orientación: acercamiento al AOI, sincronización del período y revelado de diferencias. Sin partículas de fuego, rotación constante ni animaciones de relleno.
- Etiquetas breves y concretas: qué se midió, en qué unidad, dónde, cuándo y con qué soporte.

## Tecnologías candidatas y decisión

| Opción | Papel útil | Decisión propuesta |
|---|---|---|
| CesiumJS | Globo geoespacial WGS84, imágenes y terreno, escenas temporales, vistas 3D/2D | Candidato principal si la navegación planetaria es central; comprobar densidad de datos, selección y dispositivos antes de adoptarlo |
| MapLibre + deck.gl | Cartografía vectorial y capas de datos aceleradas por GPU | Alternativa fuerte si predomina el análisis regional; la integración oficial sincroniza cámaras |
| React Three Fiber | Escenas 3D específicas dentro de React | Opcional para explicar sensores; no construir un motor GIS propio |
| Motion | Transiciones, gestos y cambios de disposición | Utilizar con moderación y respetar movimiento reducido |
| Spline | Autoría de escenas 3D | Opcional para una pieza introductoria; no es el motor del calendario ni del visor científico |

No cargar todos estos motores simultáneamente. Comparar los dos candidatos cartográficos con el mismo AOI, datos, selección y dispositivo. Medir arranque, memoria, fluidez y claridad; después fijar un motor principal. La vista GlobeView de deck.gl continúa marcada como experimental en su documentación.

## Arquitectura global sin duplicar todo el archivo de NASA

1. **Contexto cartográfico:** imágenes GIBS por teselas, con fechas y disponibilidad de capas verificadas. Son visualizaciones, no el dataset científico para entrenar o armonizar.
2. **Catálogo:** producto, plataforma, versiones, cobertura espacial y temporal, estado de descarga y huellas de integridad.
3. **Datos científicos:** almacenamiento de objetos para fuentes y GeoParquet particionado temporalmente y por bloques espaciales; índice espacial para consultas. La estrategia y el costo se dimensionan con un inventario real.
4. **Procesamiento:** trabajos separados de las peticiones web para normalización, oportunidades válidas, entrenamiento y productos agregados. Caché por AOI/período/versión.
5. **Visualización:** agregados globales de varias resoluciones; detalle bajo demanda. No enviar millones de observaciones sin filtrar como un único GeoJSON al navegador.
6. **Ciencia:** registro de validez por dominio geográfico e instrumental, pruebas reservadas por espacio y tiempo y abstención fuera de soporte. Un producto global no necesita ocultar dónde su estimación aún carece de validación.
7. **IA:** herramientas de consulta e informes sobre resultados versionados, con citas y permisos acotados. No inferir causa, propagación o respuesta operativa a partir del conteo de focos.

La versión actual necesita ampliar la ingesta, las restricciones de geometría y la validación científica; cambiar el visor por un globo no completa ese trabajo.

## Orden de ejecución propuesto

1. Fijar recorrido y estados con estos conceptos; conservar la ingestión, procedencia y API útiles de 0.1.
2. Resolver la prueba cartográfica y el contrato AOI/período/versión; incluir móvil y alternativa 2D.
3. Incorporar catálogo global, agregados y adquisición selectiva; publicar disponibilidad real.
4. Completar y validar la armonización y las oportunidades de observación en casos contrastantes.
5. Conectar calendario, laboratorio, exportación y explicación contextual.
6. Validar tareas con usuarios y preparar una demostración reproducible con datos reales.

## Criterios de aceptación de UX

- Un usuario puede localizar un área, seleccionar un período y leer su patrón estacional sin abrir documentación.
- Cambiar de vista conserva selección y contexto.
- Se distinguen cero detecciones, período incompleto y datos no disponibles.
- La procedencia de cada cifra y la referencia de armonización son accesibles desde el resultado.
- Se puede trabajar con teclado y sin gestos de arrastre; color más forma o texto.
- Móvil conserva la tarea principal y no muestra un escritorio reducido.
- El movimiento puede reducirse; no hay reproducción automática obligatoria.
- La comparación no induce a confundir puntos térmicos con incendios independientes o área quemada.

## Fuentes consultadas

- Enunciado completo entregado por el usuario en esta conversación.
- [CesiumJS](https://cesium.com/platform/cesiumjs/).
- [Integración oficial MapLibre/deck.gl](https://deck.gl/docs/developer-guide/base-maps/using-with-maplibre).
- [Limitaciones de GlobeView](https://deck.gl/docs/api-reference/core/globe-view).
- [NASA GIBS: servicios y dimensión temporal](https://nasa-gibs.github.io/gibs-api-docs/access-basics/).
- [React Three Fiber](https://r3f.docs.pmnd.rs/getting-started/introduction).
- [Motion para React](https://motion.dev/docs/react).
- [Documentación Spline](https://docs.spline.design/).
- [Guía frontend-design de Anthropic](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md).
- [Guías de interfaces web de Vercel](https://github.com/vercel-labs/web-interface-guidelines).
- [Geometría Natural Earth: dominio público](https://www.naturalearthdata.com/about/terms-of-use/), distribuida por world-atlas 2.0.2.

Los conceptos usan BlueMarble_NextGeneration de NASA GIBS como referencia estática, límites Natural Earth y puntos FIRMS ya descargados en este proyecto. No incorporan credenciales ni solicitan datos desde la vista previa.
