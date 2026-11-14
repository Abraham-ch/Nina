# NINA: product and design direction

Exploration prior to implementation. The current result, the data loaded and what remains pending are documented in [STATUS_V2.md](../docs/STATUS_V2.md).

Proposal for discussion. It does not replace version 0.1 and does not represent an implemented global harmonization. The three visual concepts use global reference cartography and a fixed real sample of 200 observations from Peru in September 2025.

## Correct scope

The challenge statement describes a planetary problem and requires a harmonized calendar for a selected area of interest and time range. It does not literally require processing every country. A global product is recommended because it widens its usefulness and fits the problem, with validation evidence published by territory, period and instrument combination.

A navigable Earth is not the same as a globally validated harmonization. Peru keeps its value as a development set and validation case. The accuracy of the exploratory Peruvian model must not be extrapolated to the rest of the planet.

## Promise and journey

**NINA lets you investigate whether fire activity changed or our way of observing it changed.**

Main journey: locate a territory → select a period → recognize its usual season → examine a difference → check observations and support → share or export evidence.

Territory and period persist when switching views. Map, calendar, comparison and explanation are parts of the same investigation. The state is kept in a reproducible link.

## Three compatible directions

### Immersive atlas

The planet takes up most of the screen, with real imagery and a visible time selection. At global scale aggregates are shown; when zooming in, relevant observations and geometries appear. Searching for a place or typing coordinates offers an alternative to gesture navigation. The globe does not spin automatically while you work.

3D helps orientation across continents and scales. Detailed analysis keeps a 2D view and avoids decorative heights that could be confused with intensity, risk or physical magnitudes.

### Visual lab

Two observers share camera and period, with slider comparison and an accessible side-by-side view. Raw and harmonized readings are identified separately. Differences in resolution and overpass time are not presented as a before/after of the same fire.

The distinctive interaction would be a substitution test: hold out one sensor during an overlap period, estimate the target with the other and reveal the held-out reference. Show error, bias, support and abstention cases. The experiment must be designed and validated before showing conclusions.

### Guided expedition

An optional tour to present to the jury: a real discontinuity in the record, its relation to the observer, the harmonization procedure and the result with its limits. Each scene opens the same analysis in the application. The user can skip it and explore freely.

## Ideas with functional value

1. **Seasonal signature of the territory.** Year × month calendar connected to the map, monthly profile and comparable historical median. Color distinguishes activity; values and labels let it be read without relying on color.
2. **Observability lens.** Separate absence of detection from absence of valid observation. Coverage is computed with the appropriate scientific products; a decorative cloud map does not replace it.
3. **Visible instrument archive.** A time band shows which platforms contributed data, version changes and partial periods. The harmonized series keeps its original observations accessible.
4. **Sensor substitution test.** The interaction described in the lab explains and demonstrates the central scientific contribution.
5. **Compare seasons across territories.** Each place is first compared with its own history. Do not rank regions of different sizes by raw counts as if they represented the same risk.
6. **Overpass explained in 3D.** A short scene helps understand footprint, resolution and overpass times. If it does not use verified ephemerides, it is labeled as a conceptual diagram.
7. **AI over the selection.** Questions such as "what changed in this period?" or "is it comparable with its history?" call bounded tools over the analysis. Each figure opens its source and each interpretation keeps its limits. A report adapted to the manager or the scientist adds more than a permanent chat.
8. **Shareable story.** Link with AOI, period, version and configuration; download of the calendar, the observations and the provenance manifest. The narrative never replaces the data.

## Visual criteria

- Territorial hierarchy: map as protagonist, compact controls and one contextual detail at a time.
- Editorial typography for titles and a readable family for analysis; aligned figures when compared.
- Deep blue as the cartographic background; neutral tones on reading surfaces; color reserved for sensors, activity and selection with a stable mapping.
- Real imagery with attribution. A composite reference map is not presented as imagery acquired on the selected date.
- Transitions that keep orientation: zoom to the AOI, period synchronization and revealing differences. No fire particles, constant rotation or filler animations.
- Short, concrete labels: what was measured, in which unit, where, when and with what support.

## Candidate technologies and decision

| Option | Useful role | Proposed decision |
|---|---|---|
| CesiumJS | WGS84 geospatial globe, imagery and terrain, temporal scenes, 3D/2D views | Main candidate if planetary navigation is central; check data density, selection and devices before adopting it |
| MapLibre + deck.gl | Vector cartography and GPU-accelerated data layers | Strong alternative if regional analysis dominates; the official integration synchronizes cameras |
| React Three Fiber | Specific 3D scenes inside React | Optional to explain sensors; do not build a custom GIS engine |
| Motion | Transitions, gestures and layout changes | Use sparingly and respect reduced motion |
| Spline | Authoring 3D scenes | Optional for an introductory piece; not the engine of the calendar or the scientific viewer |

Do not load all these engines at the same time. Compare the two cartographic candidates with the same AOI, data, selection and device. Measure startup, memory, smoothness and clarity; then settle on one main engine. deck.gl's GlobeView is still marked as experimental in its documentation.

## Global architecture without duplicating NASA's whole archive

1. **Cartographic context:** GIBS imagery as tiles, with verified layer dates and availability. These are visualizations, not the scientific dataset for training or harmonizing.
2. **Catalog:** product, platform, versions, spatial and temporal coverage, download state and integrity fingerprints.
3. **Scientific data:** object storage for sources and GeoParquet partitioned by time and by spatial blocks; spatial index for queries. Strategy and cost are sized with a real inventory.
4. **Processing:** jobs separated from web requests for normalization, valid opportunities, training and aggregated products. Cache by AOI/period/version.
5. **Visualization:** multi-resolution global aggregates; detail on demand. Do not send millions of unfiltered observations to the browser as a single GeoJSON.
6. **Science:** validity record per geographic and instrument domain, tests held out in space and time, and abstention outside support. A global product does not need to hide where its estimate still lacks validation.
7. **AI:** query and report tools over versioned results, with citations and bounded permissions. Do not infer cause, spread or operational response from hotspot counts.

The current version needs to extend ingestion, geometry constraints and scientific validation; swapping the viewer for a globe does not complete that work.

## Proposed execution order

1. Settle the journey and states with these concepts; keep the useful ingestion, provenance and API from 0.1.
2. Resolve the cartographic test and the AOI/period/version contract; include mobile and a 2D alternative.
3. Add the global catalog, aggregates and selective acquisition; publish real availability.
4. Complete and validate the harmonization and observation opportunities in contrasting cases.
5. Connect calendar, lab, export and contextual explanation.
6. Validate tasks with users and prepare a reproducible demo with real data.

## UX acceptance criteria

- A user can locate an area, select a period and read its seasonal pattern without opening documentation.
- Switching views keeps the selection and context.
- Zero detections, incomplete period and unavailable data are distinguished.
- The provenance of each figure and the harmonization reference are reachable from the result.
- Work is possible with the keyboard and without drag gestures; color plus shape or text.
- Mobile keeps the main task and does not show a shrunken desktop.
- Motion can be reduced; there is no mandatory autoplay.
- The comparison does not lead to confusing thermal points with independent fires or burned area.

## Sources consulted

- Full challenge statement provided by the user in this conversation.
- [CesiumJS](https://cesium.com/platform/cesiumjs/).
- [Official MapLibre/deck.gl integration](https://deck.gl/docs/developer-guide/base-maps/using-with-maplibre).
- [GlobeView limitations](https://deck.gl/docs/api-reference/core/globe-view).
- [NASA GIBS: services and the time dimension](https://nasa-gibs.github.io/gibs-api-docs/access-basics/).
- [React Three Fiber](https://r3f.docs.pmnd.rs/getting-started/introduction).
- [Motion for React](https://motion.dev/docs/react).
- [Spline documentation](https://docs.spline.design/).
- [Anthropic frontend-design guide](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md).
- [Vercel web interface guidelines](https://github.com/vercel-labs/web-interface-guidelines).
- [Natural Earth geometry: public domain](https://www.naturalearthdata.com/about/terms-of-use/), distributed by world-atlas 2.0.2.

The concepts use NASA GIBS BlueMarble_NextGeneration as a static reference, Natural Earth boundaries and FIRMS points already downloaded in this project. They do not include credentials or request data from the preview.
