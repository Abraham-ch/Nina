import {
  Viewer,
  Cartesian3,
  Cartesian2,
  Color,
  EllipsoidTerrainProvider,
  SingleTileImageryProvider,
  UrlTemplateImageryProvider,
  GeographicTilingScheme,
  Rectangle,
  GeoJsonDataSource,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Cartographic,
  Math as CMath,
  SceneMode,
  SceneTransforms,
  EllipsoidalOccluder,
  Ellipsoid,
} from 'cesium'
import { Globe2, Map as MapIcon, LocateFixed, PenLine, Check, X, Plus, Minus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import 'cesium/Build/Cesium/Widgets/widgets.css'
import { tr } from './i18n'
import type { Geometry, Layer, Place, Point, Selection } from './types'

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
function coordinates(geometry: Geometry) {
  const result: number[][] = []
  function walk(value: unknown) {
    if (Array.isArray(value)) {
      if (typeof value[0] === 'number') result.push(value as number[])
      else value.forEach(walk)
    }
  }
  walk(geometry.coordinates)
  return result
}
function bounds(geometry: Geometry) {
  const points = coordinates(geometry),
    longitudes = [...new Set(points.map((p) => (p[0] + 360) % 360))].sort((a, b) => a - b)
  let gap = -1,
    start = 0,
    end = 0
  for (let i = 0; i < longitudes.length; i++) {
    const next = longitudes[(i + 1) % longitudes.length] + (i === longitudes.length - 1 ? 360 : 0)
    if (next - longitudes[i] > gap) {
      gap = next - longitudes[i]
      start = next % 360
      end = longitudes[i]
    }
  }
  const full = 360 - gap > 350
  return Rectangle.fromDegrees(
    full ? -180 : start > 180 ? start - 360 : start,
    Math.min(...points.map((p) => p[1])),
    full ? 180 : end > 180 ? end - 360 : end,
    Math.max(...points.map((p) => p[1])),
  )
}
// Heat is painted on an overlaid 2D canvas with additive blending ('lighter'), as on the landing page: nearby
// hotspots add up and glow brighter. Cesium billboards average translucency, so overlapping halos darkened
// each other. VIIRS in red and MODIS in amber so the instrument stays identifiable.
const MAX_ZOOM_OUT = 24_000_000,
  HOME = Cartesian3.fromDegrees(-65, 5, 18_000_000)
type Dot = {
  pos: Cartesian3
  modis: boolean
  side: number
  point: Point
  x: number
  y: number
  on: boolean
  m: number[]
}
function glow(rgb: string) {
  const S = 64,
    c = document.createElement('canvas')
  c.width = c.height = S
  const x = c.getContext('2d')!,
    g = x.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, 'rgba(255,225,190,.9)')
  g.addColorStop(0.1, `rgba(${rgb},.7)`)
  g.addColorStop(0.38, `rgba(${rgb},.16)`)
  g.addColorStop(1, `rgba(${rgb},0)`)
  x.fillStyle = g
  x.fillRect(0, 0, S, S)
  return c
}
const gauss = () =>
  Math.sqrt(-2 * Math.log(1 - Math.random() * 0.999)) * Math.cos(2 * Math.PI * Math.random())

type Props = {
  selection: Selection
  layers: Layer[]
  compare: boolean
  split: number
  place: Place | null
  drawing: boolean
  onDrawing: (value: boolean) => void
  onGeometry: (geometry: Geometry) => void
  onInspect: (point: Point | null) => void
  flat: boolean
  onFlat: (value: boolean) => void
  busy: boolean
}
export default function Globe({
  selection,
  layers,
  compare,
  split,
  place,
  drawing,
  onDrawing,
  onGeometry,
  onInspect,
  flat,
  onFlat,
  busy,
}: Props) {
  const element = useRef<HTMLDivElement>(null),
    heat = useRef<HTMLCanvasElement>(null),
    dots = useRef<Dot[]>([]),
    compareRef = useRef(compare),
    viewer = useRef<Viewer | null>(null),
    aoi = useRef<GeoJsonDataSource | null>(null),
    vertices = useRef<number[][]>([])
  const callbacks = useRef({ onDrawing, onGeometry, onInspect })
  callbacks.current = { onDrawing, onGeometry, onInspect }
  const drawRef = useRef(drawing),
    [ready, setReady] = useState(false),
    [error, setError] = useState(''),
    [n, setN] = useState(0),
    [liveImagery, setLiveImagery] = useState(false)
  drawRef.current = drawing
  compareRef.current = compare
  const [tilesReady, setTilesReady] = useState(false)
  useEffect(() => {
    if (!element.current) return
    let disposed = false
    let observer: ResizeObserver | undefined
    let handler: ScreenSpaceEventHandler | undefined
    try {
      const v = new Viewer(element.current, {
        baseLayer: false,
        baseLayerPicker: false,
        animation: false,
        timeline: false,
        homeButton: false,
        geocoder: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        terrainProvider: new EllipsoidTerrainProvider(),
        requestRenderMode: true,
        maximumRenderTimeChange: Infinity,
        scene3DOnly: false,
        shouldAnimate: false,
        msaaSamples: 2,
        contextOptions: {
          webgl: { alpha: false, preserveDrawingBuffer: true },
        },
      })
      viewer.current = v
      v.scene.backgroundColor = Color.fromCssColorString('#050708')
      v.scene.globe.baseColor = Color.fromCssColorString('#0b1418')
      v.scene.globe.enableLighting = false
      v.scene.globe.showGroundAtmosphere = false
      if (v.scene.skyBox) v.scene.skyBox.show = false
      if (v.scene.sun) v.scene.sun.show = false
      if (v.scene.moon) v.scene.moon.show = false
      if (v.scene.skyAtmosphere) v.scene.skyAtmosphere.show = true
      v.scene.fog.enabled = false
      v.resolutionScale = Math.min(window.devicePixelRatio, 1.5)
      v.scene.screenSpaceCameraController.minimumZoomDistance = 10000
      v.scene.screenSpaceCameraController.maximumZoomDistance = MAX_ZOOM_OUT
      v.scene.globe.maximumScreenSpaceError = 1
      v.camera.setView({ destination: HOME })
      SingleTileImageryProvider.fromUrl('/assets/earth-reference.jpg', {
        credit: 'NASA GIBS / ESDIS · Blue Marble de referencia',
      })
        .then((provider) => {
          if (disposed) return
          v.imageryLayers.addImageryProvider(provider, 0)
          v.scene.requestRender()
        })
        .catch(() => {})
      const tiles = new UrlTemplateImageryProvider({
        url: '/api/imagery/blue-marble/{z}/{x}/{y}.jpg',
        tilingScheme: new GeographicTilingScheme(),
        maximumLevel: 8,
        tileWidth: 512,
        tileHeight: 512,
        credit: 'NASA GIBS · imagen de referencia, no adquirida en la fecha seleccionada',
      })
      const tileLayer = v.imageryLayers.addImageryProvider(tiles)
      tileLayer.brightness = 0.91
      tileLayer.contrast = 1.08
      tiles.errorEvent.addEventListener(() => {
        if (!disposed) setLiveImagery(false)
      })
      v.scene.globe.tileLoadProgressEvent.addEventListener((count: number) => {
        if (!disposed && count === 0) {
          setLiveImagery(true)
          setTilesReady(true)
        }
      })
      setTimeout(() => {
        if (!disposed) setTilesReady(true)
      }, 9000) // ponytail: if the tiles never finish, do not block the map
      const red = glow('255,64,32'),
        amber = glow('255,170,50'),
        scratch = new Cartesian2()
      const paint = () => {
        const c = heat.current
        if (!c) return
        const w = c.clientWidth,
          h = c.clientHeight,
          dpr = Math.min(devicePixelRatio || 1, 2)
        if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
          c.width = Math.round(w * dpr)
          c.height = Math.round(h * dpr)
        }
        const ctx = c.getContext('2d')!
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        ctx.clearRect(0, 0, w, h)
        const list = dots.current
        if (!list.length || v.scene.mode === SceneMode.MORPHING) return
        const occ =
          v.scene.mode === SceneMode.SCENE3D
            ? new EllipsoidalOccluder(Ellipsoid.WGS84, v.camera.positionWC)
            : null
        const r = Math.max(
            4,
            Math.min(
              30,
              11 * Math.pow(2e6 / Math.max(1, v.camera.positionCartographic.height), 0.36),
            ),
          ),
          cut = w * v.scene.splitPosition,
          split = compareRef.current
        ctx.globalCompositeOperation = 'lighter'
        ctx.globalAlpha = 0.32
        for (const d of list) {
          d.on = false
          if (occ && !occ.isPointVisible(d.pos)) continue
          const p = SceneTransforms.worldToWindowCoordinates(v.scene, d.pos, scratch)
          if (
            !p ||
            p.x < -r ||
            p.y < -r ||
            p.x > w + r ||
            p.y > h + r ||
            (split && (d.side === 0 ? p.x > cut : p.x < cut))
          )
            continue
          d.x = p.x
          d.y = p.y
          d.on = true
          ctx.drawImage(d.modis ? amber : red, p.x - r, p.y - r, r * 2, r * 2)
        }
        // Motes: two particles per detection around the core, for the cloud texture.
        ctx.globalAlpha = 0.85
        const spread = r * 0.38
        for (const modis of [false, true]) {
          ctx.fillStyle = modis ? '#ffd08a' : '#ff9a6a'
          ctx.beginPath()
          for (const d of list)
            if (d.on && d.modis === modis) {
              ctx.rect(d.x + d.m[0] * spread, d.y + d.m[1] * spread, 1.4, 1.4)
              ctx.rect(d.x + d.m[2] * spread, d.y + d.m[3] * spread, 1.2, 1.2)
            }
          ctx.fill()
        }
      }
      v.scene.postRender.addEventListener(paint)
      handler = new ScreenSpaceEventHandler(v.scene.canvas)
      handler.setInputAction((event: { position: Cartesian2 }) => {
        if (drawRef.current) {
          const ray = v.camera.getPickRay(event.position)
          const cartesian = ray && v.scene.globe.pick(ray, v.scene)
          if (!cartesian) return
          const pos = Cartographic.fromCartesian(cartesian)
          vertices.current.push([CMath.toDegrees(pos.longitude), CMath.toDegrees(pos.latitude)])
          setN(vertices.current.length)
          const line = v.entities.getById('drawing')
          if (line) v.entities.remove(line)
          if (vertices.current.length >= 2)
            v.entities.add({
              id: 'drawing',
              polyline: {
                positions: Cartesian3.fromDegreesArray(vertices.current.flat()),
                width: 2,
                material: Color.fromCssColorString('#f3c27b'),
              },
            })
          v.scene.requestRender()
          return
        }
        let best: Dot | null = null,
          bestD = 144
        for (const d of dots.current) {
          if (!d.on) continue
          const dd = (d.x - event.position.x) ** 2 + (d.y - event.position.y) ** 2
          if (dd < bestD) {
            bestD = dd
            best = d
          }
        }
        callbacks.current.onInspect(best ? best.point : null)
      }, ScreenSpaceEventType.LEFT_CLICK)
      v.screenSpaceEventHandler.removeInputAction(ScreenSpaceEventType.LEFT_DOUBLE_CLICK)
      observer = new ResizeObserver(() => {
        if (!v.isDestroyed()) {
          v.resize()
          v.scene.requestRender()
        }
      })
      observer.observe(element.current)
      setReady(true)
    } catch {
      setError(
        tr(
          'The 3D viewer could not start on this device. You can still pick a territory and use the calendar and coordinates.',
          'El visor 3D no pudo iniciarse en este dispositivo. Puedes seleccionar un territorio y usar el calendario y las coordenadas.',
        ),
      )
    }
    return () => {
      disposed = true
      observer?.disconnect()
      handler?.destroy()
      if (viewer.current && !viewer.current.isDestroyed()) viewer.current.destroy()
      viewer.current = null
    }
  }, [])
  useEffect(() => {
    const v = viewer.current
    if (!ready || !v) return
    const list: Dot[] = []
    for (const [index, layer] of layers.entries())
      for (const point of layer.points.features) {
        const [lon, lat] = point.geometry.coordinates
        list.push({
          pos: Cartesian3.fromDegrees(lon, lat, 0),
          modis: layer.source === 'modis',
          side: index,
          point,
          x: 0,
          y: 0,
          on: false,
          m: [gauss(), gauss(), gauss(), gauss()],
        })
      }
    dots.current = list
    v.scene.requestRender()
  }, [ready, layers, compare])
  useEffect(() => {
    const v = viewer.current
    if (!v || !ready) return
    v.scene.splitPosition = split / 100
    v.scene.requestRender()
  }, [split, ready])
  useEffect(() => {
    const v = viewer.current
    if (!v || !ready) return
    if (flat && v.scene.mode !== SceneMode.SCENE2D) v.scene.morphTo2D(reduced() ? 0 : 0.7)
    else if (!flat && v.scene.mode !== SceneMode.SCENE3D) v.scene.morphTo3D(reduced() ? 0 : 0.7)
  }, [flat, ready])
  const areaKey = JSON.stringify([selection.scope, selection.department, selection.geometry])
  useEffect(() => {
    const v = viewer.current
    if (!v || !ready) return
    let active = true
    if (aoi.current) {
      v.dataSources.remove(aoi.current, true)
      aoi.current = null
    }
    const geometry = selection.geometry || place?.geometry
    if (geometry) {
      GeoJsonDataSource.load(
        { type: 'Feature', geometry, properties: {} },
        {
          stroke: Color.fromCssColorString('#4fe08a'),
          strokeWidth: 2,
          fill: Color.fromCssColorString('#4fe08a').withAlpha(0.03),
          clampToGround: false,
        },
      )
        .then((source) => {
          if (!active || v.isDestroyed()) return
          aoi.current = source
          v.dataSources.add(source)
          v.scene.requestRender()
        })
        .catch(() => {})
      v.camera.flyTo({
        destination: bounds(geometry),
        duration: reduced() ? 0 : 1.1,
      })
    } else if (selection.scope === 'PER')
      v.camera.flyTo({
        destination: Rectangle.fromDegrees(-83, -20, -67, 2),
        duration: reduced() ? 0 : 1.1,
      })
    else
      v.camera.flyTo({
        destination: HOME,
        duration: reduced() ? 0 : 1.1,
      })
    return () => {
      active = false
    }
  }, [areaKey, ready, place?.properties.id])
  useEffect(() => {
    if (!drawing) {
      vertices.current = []
      setN(0)
      const v = viewer.current
      const entity = v?.entities.getById('drawing')
      if (entity) v?.entities.remove(entity)
      v?.scene.requestRender()
    }
  }, [drawing])
  function finish() {
    if (vertices.current.length < 3) return
    const ring = [...vertices.current, vertices.current[0]]
    callbacks.current.onGeometry({ type: 'Polygon', coordinates: [ring] })
    callbacks.current.onDrawing(false)
  }
  function center() {
    const v = viewer.current
    if (!v) return
    if (selection.geometry)
      v.camera.flyTo({
        destination: bounds(selection.geometry),
        duration: reduced() ? 0 : 0.7,
      })
    else if (selection.scope === 'PER')
      v.camera.flyTo({
        destination: Rectangle.fromDegrees(-83, -20, -67, 2),
        duration: reduced() ? 0 : 0.7,
      })
    else
      v.camera.flyTo({
        destination: HOME,
        duration: reduced() ? 0 : 0.7,
      })
  }
  return (
    <>
      <div
        ref={element}
        className="earth-canvas"
        aria-label={tr(
          'World geospatial viewer. Use the territory controls as an alternative to gestures.',
          'Visor geoespacial mundial. Usa los controles de territorio como alternativa a los gestos.',
        )}
      >
        <canvas ref={heat} className="heat-layer" aria-hidden="true" />
      </div>
      {!error && !tilesReady && (
        <div className="globe-loader" role="status">
          <span className="spinner" />
          {tr('Preparing the map…', 'Preparando el mapa…')}
        </div>
      )}
      {!error && tilesReady && busy && (
        <div className="globe-busy" role="status">
          <span className="spinner" />
          {tr('Loading detections…', 'Cargando detecciones…')}
        </div>
      )}
      {error && (
        <div className="map-fallback">
          <img
            src="/assets/earth-reference.jpg"
            alt={tr('NASA world reference cartography', 'Cartografía mundial de referencia NASA')}
          />
          <p role="status">{error}</p>
        </div>
      )}
      <div className="map-tools" aria-label={tr('Map tools', 'Herramientas del mapa')}>
        <button
          aria-label={
            flat
              ? tr('Switch to 3D globe', 'Cambiar a globo 3D')
              : tr('Switch to 2D map', 'Cambiar a mapa 2D')
          }
          onClick={() => onFlat(!flat)}
          disabled={!ready}
        >
          {flat ? <Globe2 size={17} /> : <MapIcon size={17} />}
          <span>{flat ? '3D' : '2D'}</span>
        </button>
        <button
          aria-label={tr('Center selection', 'Centrar selección')}
          onClick={center}
          disabled={!ready}
        >
          <LocateFixed size={17} />
        </button>
        <button
          aria-label={tr('Zoom in', 'Acercar')}
          onClick={() => {
            viewer.current?.camera.zoomIn(
              (viewer.current?.camera.positionCartographic.height || 1e6) * 0.4,
            )
            viewer.current?.scene.requestRender()
          }}
          disabled={!ready}
        >
          <Plus size={17} />
        </button>
        <button
          aria-label={tr('Zoom out', 'Alejar')}
          onClick={() => {
            const v = viewer.current
            if (!v) return
            const h = v.camera.positionCartographic.height
            v.camera.zoomOut(Math.max(0, Math.min(h * 0.5, MAX_ZOOM_OUT - h)))
            v.scene.requestRender()
          }}
          disabled={!ready}
        >
          <Minus size={17} />
        </button>
        <button
          aria-label={tr('Draw an area', 'Dibujar un área')}
          aria-pressed={drawing}
          onClick={() => onDrawing(!drawing)}
          disabled={!ready}
        >
          <PenLine size={17} />
        </button>
      </div>
      {drawing && (
        <div className="draw-help" role="status">
          <span>
            {tr(
              `Add vertices on the map · ${n} points`,
              `Añade vértices sobre el mapa · ${n} puntos`,
            )}
          </span>
          <button onClick={finish} disabled={n < 3}>
            <Check size={15} />
            {tr('Apply area', 'Aplicar área')}
          </button>
          <button
            onClick={() => onDrawing(false)}
            aria-label={tr('Cancel drawing', 'Cancelar dibujo')}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <span className="imagery-credit">
        NASA GIBS ·{' '}
        {liveImagery
          ? tr('reference tiles', 'teselas de referencia')
          : tr('global reference', 'referencia global')}{' '}
        · WGS84
      </span>
    </>
  )
}
