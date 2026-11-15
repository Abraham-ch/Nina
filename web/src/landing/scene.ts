// Landing scene: the planet and Peru as one large scatter plot in real coordinates.
// Every particle lives in degrees (lon, lat); the view interpolates between the world frame and the Peru frame,
// so the axes always measure true positions. The hotspots are real VIIRS NOAA-20 detections.

export type Ring = [number, number][]
export type Cell = [number, number, number, number] // i, j (celda de 0,1°), detecciones, FRP sumada
export interface Week {
  week: string
  count: number
  frp: number
  partial: boolean
  cells: Cell[]
}
export interface LandingData {
  source: string
  platform: string
  first_date: string
  last_date: string
  detections: number
  cell_degrees: number
  bounds: [number, number, number, number]
  outline: Ring[]
  peak_week: string
  peak_count: number
  departments: { name: string; count: number; outline: Ring[] | null }[]
  night: number
  weeks: Week[]
  note: string
}
interface Feature {
  properties: { name?: string }
  geometry: { type: string; coordinates: unknown }
}
export interface Countries {
  features: Feature[]
}

type Box = [number, number, number, number] // oeste, sur, este, norte
type Rect = { x: number; y: number; w: number; h: number }
type View = { cx: number; cy: number; sx: number; sy: number; k: number } // centro geo, centro en pantalla, px/°

const WORLD: Box = [-180, -58, 180, 84]
const PERU_CENTER = [-75, -9.4]
const KM_PER_DEG_LAT = 110.574
const LAND = 9000,
  DUST = 1100,
  PERU_DUST = 260
const WEEK_SECONDS = 0.75
const WOBBLE = 1 // particle float scale (px); raise or lower it to tune

const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v))
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const smooth = (t: number) => t * t * (3 - 2 * t)
const gauss = () =>
  Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random())
import { locale, tr } from '../i18n'

const fmt = { format: (n: number) => n.toLocaleString(locale()) }

export const weekLabel = (iso: string) =>
  new Date(iso + 'T00:00:00Z').toLocaleDateString(locale(), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })

function ringsOf(feature: Feature): Ring[] {
  const g = feature.geometry
  if (g.type === 'Polygon') return g.coordinates as Ring[]
  if (g.type === 'MultiPolygon') return (g.coordinates as Ring[][]).flat()
  return []
}

/** Rasterizes in equirectangular and returns the RGBA channel used to sample particles. */
function raster(
  box: Box,
  ppd: number,
  paint: (
    ctx: CanvasRenderingContext2D,
    px: (lon: number, lat: number) => [number, number],
  ) => void,
) {
  const w = Math.ceil((box[2] - box[0]) * ppd),
    h = Math.ceil((box[3] - box[1]) * ppd)
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  paint(ctx, (lon, lat) => [(lon - box[0]) * ppd, (box[3] - lat) * ppd])
  return { data: ctx.getImageData(0, 0, w, h).data, w, h, ppd, box }
}

function fillRings(
  ctx: CanvasRenderingContext2D,
  rings: Ring[],
  px: (lon: number, lat: number) => [number, number],
  color: string,
) {
  ctx.beginPath()
  for (const ring of rings)
    ring.forEach(([lon, lat], i) => {
      const [x, y] = px(lon, lat)
      if (i) ctx.lineTo(x, y)
      else ctx.moveTo(x, y)
    })
  ctx.fillStyle = color
  ctx.fill('evenodd')
}

function fit(box: Box, r: Rect): View {
  const k = Math.min(r.w / (box[2] - box[0]), r.h / (box[3] - box[1]))
  return {
    cx: (box[0] + box[2]) / 2,
    cy: (box[1] + box[3]) / 2,
    sx: r.x + r.w / 2,
    sy: r.y + r.h / 2,
    k,
  }
}

function mix(a: View, b: View, t: number): View {
  const l = (p: number, q: number) => p + (q - p) * t
  return {
    cx: l(a.cx, b.cx),
    cy: l(a.cy, b.cy),
    sx: l(a.sx, b.sx),
    sy: l(a.sy, b.sy),
    k: a.k * Math.pow(b.k / a.k, t),
  }
}

function inside(x: number, y: number, rings: Ring[]) {
  let hit = false
  for (const r of rings)
    for (let i = 0, j = r.length - 1; i < r.length; j = i++)
      if (
        r[i][1] > y !== r[j][1] > y &&
        x < ((r[j][0] - r[i][0]) * (y - r[i][1])) / (r[j][1] - r[i][1]) + r[i][0]
      )
        hit = !hit
  return hit
}

function niceStep(span: number, target: number, steps: number[]) {
  return steps.find((s) => span / s <= target) ?? steps[steps.length - 1]
}

export interface Scene {
  destroy(): void
}
export interface SceneHooks {
  /** Scroll progress computed by the page: morph 0 = world, 1 = Peru; stage 1 = Peru centered between
   *  the indicators; focus = active indicator (-1 none): 0 season, 1 critical weeks, 2 regions, 3 peak. */
  progress(): {
    morph: number
    fire: number
    dim: number
    stage: number
    focus: number
  }
  onWeek(week: Week, index: number): void
}

export function createScene(
  canvas: HTMLCanvasElement,
  countries: Countries,
  data: LandingData | null,
  hooks: SceneHooks,
): Scene {
  const ctx = canvas.getContext('2d')!
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches // only sets the initial week
  const peruRings: Ring[] =
    data?.outline ?? ringsOf(countries.features.find((f) => f.properties.name === 'Peru')!)
  const peruBox: Box = data ? data.bounds : [-81.4, -18.4, -68.6, 0]

  // --- Planet particles (A) and their destination on the Peru outline (B) ---------------------------------
  const world = raster(WORLD, 4, (c, px) => {
    for (const f of countries.features) fillRings(c, ringsOf(f), px, '#fff')
    fillRings(c, peruRings, px, '#0f0')
  })
  const ax = new Float32Array(LAND),
    ay = new Float32Array(LAND),
    peruA = new Uint8Array(LAND)
  for (let n = 0, tries = 0; n < LAND && tries < 400000; tries++) {
    const lon = WORLD[0] + Math.random() * (WORLD[2] - WORLD[0]),
      lat = WORLD[1] + Math.random() * (WORLD[3] - WORLD[1])
    const x = Math.floor((lon - WORLD[0]) * world.ppd),
      y = Math.floor((WORLD[3] - lat) * world.ppd),
      o = (y * world.w + x) * 4
    if (world.data[o + 3] < 128) continue
    ax[n] = lon
    ay[n] = lat
    peruA[n] = world.data[o] < 80 && world.data[o + 1] > 160 ? 1 : 0
    n++
  }

  // Destinations: 62 % on the perimeter (cloud with Gaussian spread), 38 % faint fill.
  const segments: [number, number, number, number][] = [],
    cumulative: number[] = []
  let length = 0
  for (const ring of peruRings)
    for (let i = 1; i < ring.length; i++) {
      const [x0, y0] = ring[i - 1],
        [x1, y1] = ring[i]
      length += Math.hypot(x1 - x0, y1 - y0)
      segments.push([x0, y0, x1, y1])
      cumulative.push(length)
    }
  const peruFill = raster(peruBox, 40, (c, px) => fillRings(c, peruRings, px, '#fff'))
  const targets: { x: number; y: number; edge: number }[] = []
  const edgeCount = Math.round(LAND * 0.62)
  for (let n = 0; n < edgeCount; n++) {
    const u = Math.random() * length
    let lo = 0,
      hi = cumulative.length - 1
    while (lo < hi) {
      const m = (lo + hi) >> 1
      if (cumulative[m] < u) lo = m + 1
      else hi = m
    }
    const [x0, y0, x1, y1] = segments[lo],
      seg = Math.hypot(x1 - x0, y1 - y0) || 1
    const t = seg ? 1 - (cumulative[lo] - u) / seg : 0,
      spread = Math.random() < 0.12 ? 0.16 : 0.035
    const d = gauss() * spread
    targets.push({
      x: x0 + (x1 - x0) * t - ((y1 - y0) / seg) * d,
      y: y0 + (y1 - y0) * t + ((x1 - x0) / seg) * d,
      edge: 1,
    })
  }
  for (let tries = 0; targets.length < LAND && tries < 400000; tries++) {
    const x = Math.random() * peruFill.w,
      y = Math.random() * peruFill.h
    if (peruFill.data[(Math.floor(y) * peruFill.w + Math.floor(x)) * 4 + 3] < 128) continue
    targets.push({
      x: peruBox[0] + x / peruFill.ppd,
      y: peruBox[3] - y / peruFill.ppd,
      edge: 0,
    })
  }
  // The angular sector relative to Peru is kept: the planet "contracts" onto the outline without paths crossing.
  const angle = (x: number, y: number) => Math.atan2(y - PERU_CENTER[1], x - PERU_CENTER[0])
  const order = Array.from({ length: LAND }, (_, i) => i).sort(
    (a, b) => angle(ax[a], ay[a]) - angle(ax[b], ay[b]),
  )
  targets.sort((a, b) => angle(a.x, a.y) - angle(b.x, b.y))
  const bx = new Float32Array(LAND),
    by = new Float32Array(LAND),
    edge = new Uint8Array(LAND)
  const delay = new Float32Array(LAND),
    arc = new Float32Array(LAND),
    size = new Float32Array(LAND),
    alpha = new Float32Array(LAND)
  const phase = new Float32Array(LAND),
    freq = new Float32Array(LAND)
  order.forEach((p, i) => {
    const t = targets[Math.min(i, targets.length - 1)]
    bx[p] = t.x
    by[p] = t.y
    edge[p] = t.edge
    delay[p] = Math.random() * 0.42
    arc[p] = gauss() * 0.18
    phase[p] = Math.random() * Math.PI * 2
    freq[p] = 0.6 + Math.random() * 1.1 // float: rad/s
    size[p] = 0.9 + Math.random() * 0.9
    alpha[p] = 0.3 + Math.random() * 0.55
  })

  // Dust: fixed scattered points that give the cloud texture (they do not move; only the view moves them).
  const dust = Array.from({ length: DUST + PERU_DUST }, (_, i) =>
    i < DUST
      ? {
          x: -180 + Math.random() * 360,
          y: -58 + Math.random() * 142,
          a: 0.05 + Math.random() * 0.2,
        }
      : {
          x: -86 + Math.random() * 22,
          y: -22 + Math.random() * 26,
          a: 0.05 + Math.random() * 0.18,
        },
  )

  // --- Hotspots: weekly series per cell --------------------------------------------------------------------
  const weeks = data?.weeks ?? []
  const cellIndex = new Map<number, number>(),
    cellLon: number[] = [],
    cellLat: number[] = [],
    series: Float32Array[] = []
  weeks.forEach((w, wi) =>
    w.cells.forEach(([i, j, n]) => {
      const key = i * 100000 + j
      let c = cellIndex.get(key)
      if (c === undefined) {
        c = series.length
        cellIndex.set(key, c)
        cellLon.push(i * data!.cell_degrees)
        cellLat.push(j * data!.cell_degrees)
        series.push(new Float32Array(weeks.length))
      }
      series[c][wi] = n
    }),
  )
  const peakIndex = Math.max(
    0,
    weeks.findIndex((w) => w.week === data?.peak_week),
  )
  // Weeks the animation walks through for the active indicator (same computation as the page figures).
  const all = weeks.map((_, i) => i),
    total = weeks.reduce((s, w) => s + w.count, 0)
  const full = all.filter((i) => !weeks[i].partial).sort((a, b) => weeks[b].count - weeks[a].count)
  const critical: number[] = []
  for (let acc = 0, k = 0; acc < total / 2 && k < full.length; k++) {
    critical.push(full[k])
    acc += weeks[full[k]].count
  }
  const medianIndex = full[Math.floor(full.length / 2)] ?? 0
  const season = all.filter((i) => {
    const m = new Date(weeks[i].week + 'T00:00:00Z').getUTCMonth()
    return m >= 6 && m <= 9
  })
  const sequences: number[][] = [
    season,
    [...critical].sort((a, b) => a - b),
    season,
    [medianIndex, peakIndex],
  ]
  const highlight: Set<number>[] = [
    new Set(season),
    new Set(critical),
    new Set(),
    new Set([medianIndex, peakIndex]),
  ]
  const regions = (data?.departments ?? [])
    .filter((d) => d.outline)
    .map((d) => ({ name: d.name, rings: d.outline! }))
  const cellRegion = cellLon.map((x, c) =>
    regions.some((r) => inside(x, cellLat[c], r.rings)) ? 1 : 0,
  )
  const sprite = document.createElement('canvas')
  sprite.width = sprite.height = 64
  {
    const s = sprite.getContext('2d')!,
      g = s.createRadialGradient(32, 32, 0, 32, 32, 32)
    g.addColorStop(0, 'rgba(255,238,210,1)')
    g.addColorStop(0.16, 'rgba(255,104,52,.95)')
    g.addColorStop(0.42, 'rgba(255,44,22,.32)')
    g.addColorStop(1, 'rgba(255,30,20,0)')
    s.fillStyle = g
    s.fillRect(0, 0, 64, 64)
  }

  // --- Layout ---------------------------------------------------------------------------------------------
  let W = 0,
    H = 0,
    plot: Rect = { x: 0, y: 0, w: 0, h: 0 },
    worldView = fit(WORLD, plot),
    peruView = worldView,
    centerView = worldView,
    wide = true
  function layout() {
    const dpr = Math.min(2, devicePixelRatio || 1)
    W = canvas.clientWidth
    H = canvas.clientHeight
    wide = W >= 900
    canvas.width = Math.round(W * dpr)
    canvas.height = Math.round(H * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const m = W >= 640 ? { t: 92, r: 86, b: 104, l: 80 } : { t: 84, r: 22, b: 96, l: 44 }
    plot = { x: m.l, y: m.t, w: W - m.l - m.r, h: H - m.t - m.b }
    worldView = fit(WORLD, plot)
    const pad: Box = [peruBox[0] - 1.2, peruBox[1] - 1, peruBox[2] + 1.2, peruBox[3] + 1]
    peruView = fit(
      pad,
      wide
        ? {
            x: plot.x + plot.w * 0.4,
            y: plot.y,
            w: plot.w * 0.6,
            h: plot.h,
          }
        : {
            x: plot.x,
            y: plot.y + plot.h * 0.34,
            w: plot.w,
            h: plot.h * 0.66,
          },
    )
    // Third scene: Peru is centered and shrunk to leave room for the indicators on both sides.
    centerView = fit(
      pad,
      wide
        ? {
            x: plot.x + plot.w * 0.34,
            y: plot.y + plot.h * 0.1,
            w: plot.w * 0.32,
            h: plot.h * 0.8,
          }
        : { x: plot.x, y: plot.y + 8, w: plot.w, h: plot.h * 0.46 },
    )
  }
  layout()
  const observer = new ResizeObserver(layout)
  observer.observe(canvas)

  // --- Dibujo ---------------------------------------------------------------------------------------------
  const bucketCount = 4 * 9 * 8,
    bucketSize = new Int32Array(bucketCount),
    bucketStart = new Int32Array(bucketCount + 1)
  const bucketOf = new Int16Array(LAND),
    sorted = new Int32Array(LAND),
    sx = new Float32Array(LAND),
    sy = new Float32Array(LAND)
  const styles = new Map<number, string>()
  const START = [
      [205, 218, 232],
      [79, 224, 138],
    ],
    END = [
      [79, 224, 138],
      [79, 224, 138],
    ]
  function styleFor(b: number) {
    let s = styles.get(b)
    if (!s) {
      const aq = b % 8,
        tq = Math.floor(b / 8) % 9,
        kind = Math.floor(b / 72),
        fromPeru = kind >> 1,
        isEdge = kind & 1,
        t = tq / 8
      const from = START[fromPeru],
        to = END[isEdge],
        a0 = (aq + 0.5) / 8,
        a1 = isEdge ? 0.9 : 0.2
      const c = from.map((v, i) => Math.round(v + (to[i] - v) * t))
      s = `rgba(${c[0]},${c[1]},${c[2]},${(a0 + (a1 - a0) * t).toFixed(3)})`
      styles.set(b, s)
    }
    return s
  }

  function axes(view: View, alpha: number, fire: number) {
    const lonAt = (x: number) => view.cx + (x - view.sx) / view.k,
      latAt = (y: number) => view.cy - (y - view.sy) / view.k
    const X = (lon: number) => view.sx + (lon - view.cx) * view.k,
      Y = (lat: number) => view.sy - (lat - view.cy) * view.k
    const w0 = lonAt(plot.x),
      w1 = lonAt(plot.x + plot.w),
      s0 = latAt(plot.y + plot.h),
      s1 = latAt(plot.y)
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = 'rgba(232,238,240,.7)'
    ctx.fillStyle = 'rgba(232,238,240,.78)'
    ctx.lineWidth = 1
    ctx.font = "11px 'IBM Plex Sans', Arial, sans-serif"
    // Ecuador como referencia medida.
    if (s0 < 0 && s1 > 0) {
      ctx.save()
      ctx.setLineDash([2, 6])
      ctx.strokeStyle = 'rgba(232,238,240,.14)'
      ctx.beginPath()
      ctx.moveTo(plot.x, Y(0))
      ctx.lineTo(plot.x + plot.w, Y(0))
      ctx.stroke()
      ctx.restore()
      ctx.fillStyle = 'rgba(232,238,240,.38)'
      ctx.textAlign = 'left'
      ctx.fillText(tr('Equator · 0°', 'Ecuador · 0°'), plot.x + 8, Y(0) - 6)
      ctx.fillStyle = 'rgba(232,238,240,.78)'
    }
    const top = plot.y - 22,
      steps = [1, 2, 5, 10, 15, 30, 60]
    const lonStep = niceStep(w1 - w0, Math.max(3, plot.w / 120), steps)
    ctx.textAlign = 'center'
    for (let v = Math.ceil(w0 / lonStep) * lonStep; v <= w1; v += lonStep) {
      const x = X(v)
      ctx.beginPath()
      ctx.moveTo(x, top)
      ctx.lineTo(x, top + 6)
      ctx.stroke()
      ctx.fillText(v === 0 ? '0°' : `${Math.abs(v)}°${v < 0 ? tr('W', 'O') : 'E'}`, x, top - 6)
    }
    ctx.font = "12px 'IBM Plex Sans', Arial, sans-serif"
    title(
      plot.x + plot.w / 2,
      top - 28,
      0,
      tr('← west', '← oeste'),
      tr('Longitude', 'Longitud'),
      tr('east →', 'este →'),
    )
    ctx.font = "11px 'IBM Plex Sans', Arial, sans-serif"
    const latStep = niceStep(s1 - s0, Math.max(3, plot.h / 80), steps),
      left = plot.x - 26
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    for (let v = Math.ceil(s0 / latStep) * latStep; v <= s1; v += latStep) {
      const y = Y(v)
      ctx.beginPath()
      ctx.moveTo(left, y)
      ctx.lineTo(left + 6, y)
      ctx.stroke()
      ctx.fillText(v === 0 ? '0°' : `${Math.abs(v)}°${v < 0 ? 'S' : 'N'}`, left - 5, y)
    }
    ctx.font = "12px 'IBM Plex Sans', Arial, sans-serif"
    title(
      left - 44,
      plot.y + plot.h / 2,
      -Math.PI / 2,
      tr('← south', '← sur'),
      tr('Latitude', 'Latitud'),
      tr('north →', 'norte →'),
    )
    if (W >= 640) {
      // Right axis: meridian distance to the equator (≈ 110.574 km per degree of latitude).
      ctx.font = "11px 'IBM Plex Sans', Arial, sans-serif"
      ctx.textAlign = 'left'
      const k0 = s0 * KM_PER_DEG_LAT,
        k1 = s1 * KM_PER_DEG_LAT,
        right = plot.x + plot.w + 22
      const kmStep = niceStep(
        k1 - k0,
        Math.max(3, plot.h / 80),
        [100, 200, 250, 500, 1000, 2000, 2500, 5000],
      )
      for (let v = Math.ceil(k0 / kmStep) * kmStep; v <= k1; v += kmStep) {
        const y = Y(v / KM_PER_DEG_LAT)
        ctx.beginPath()
        ctx.moveTo(right - 6, y)
        ctx.lineTo(right, y)
        ctx.stroke()
        ctx.fillText(`${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt.format(Math.abs(v))}`, right + 5, y)
      }
      ctx.font = "12px 'IBM Plex Sans', Arial, sans-serif"
      title(
        right + 62,
        plot.y + plot.h / 2,
        -Math.PI / 2,
        tr('← south', '← sur'),
        tr('Distance to the equator, km', 'Distancia al ecuador, km'),
        tr('north →', 'norte →'),
      )
    }
    ctx.restore()
    if (fire > 0 && weeks.length) timeline(fire)
  }

  function title(
    x: number,
    y: number,
    rotation: number,
    before: string,
    bold: string,
    after: string,
  ) {
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rotation)
    ctx.textBaseline = 'middle'
    const regular = "12px 'IBM Plex Sans', Arial, sans-serif",
      strong = "600 12px 'IBM Plex Sans', Arial, sans-serif"
    ctx.font = regular
    const a = ctx.measureText(before + '  ').width,
      c = ctx.measureText('  ' + after).width
    ctx.font = strong
    const b = ctx.measureText(bold).width
    let cursor = -(a + b + c) / 2
    ctx.textAlign = 'left'
    ctx.font = regular
    ctx.fillStyle = 'rgba(232,238,240,.55)'
    ctx.fillText(before + '  ', cursor, 0)
    cursor += a
    ctx.font = strong
    ctx.fillStyle = 'rgba(244,247,248,.95)'
    ctx.fillText(bold, cursor, 0)
    cursor += b
    ctx.font = regular
    ctx.fillStyle = 'rgba(232,238,240,.55)'
    ctx.fillText('  ' + after, cursor, 0)
    ctx.restore()
  }

  let weekFloat = reduced ? peakIndex : 0,
    lastWeek = -1,
    focus = -1,
    current = 0
  function timeline(alpha: number) {
    const peak = Math.max(1, ...weeks.map((w) => w.count)),
      base = H - 44,
      x0 = plot.x,
      width = plot.w,
      bw = width / weeks.length
    const lit = focus >= 0 ? highlight[focus] : null
    ctx.save()
    ctx.globalAlpha = alpha
    weeks.forEach((w, i) => {
      const h = Math.max(1, (w.count / peak) * 34),
        x = x0 + i * bw
      ctx.fillStyle =
        i === current
          ? 'rgba(255,92,52,.95)'
          : lit?.size && lit.has(i)
            ? 'rgba(255,128,80,.85)'
            : lit?.size
              ? 'rgba(255,92,52,.14)'
              : w.partial
                ? 'rgba(255,92,52,.22)'
                : 'rgba(255,92,52,.45)'
      ctx.fillRect(x + bw * 0.18, base - h, bw * 0.64, h)
      if (w.partial) {
        ctx.strokeStyle = 'rgba(255,92,52,.5)'
        ctx.setLineDash([2, 2])
        ctx.strokeRect(x + bw * 0.18, base - h, bw * 0.64, h)
        ctx.setLineDash([])
      }
    })
    ctx.strokeStyle = 'rgba(232,238,240,.7)'
    ctx.fillStyle = 'rgba(232,238,240,.78)'
    ctx.lineWidth = 1
    ctx.font = "11px 'IBM Plex Sans', Arial, sans-serif"
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.beginPath()
    ctx.moveTo(x0, base + 0.5)
    ctx.lineTo(x0 + width, base + 0.5)
    ctx.stroke()
    let month = -1
    weeks.forEach((w, i) => {
      const d = new Date(w.week + 'T00:00:00Z')
      if (d.getUTCMonth() === month) return
      month = d.getUTCMonth()
      const x = x0 + i * bw
      ctx.beginPath()
      ctx.moveTo(x, base)
      ctx.lineTo(x, base + 5)
      ctx.stroke()
      const label = d
        .toLocaleDateString(locale(), {
          month: 'short',
          timeZone: 'UTC',
        })
        .replace('.', '')
      if ((width / weeks.length) * 4 > 22)
        ctx.fillText(
          month === 0 || i === 0 ? `${label} ${d.getUTCFullYear()}` : label,
          x + 2 * bw,
          base + 8,
        )
    })
    ctx.textAlign = 'right'
    ctx.fillStyle = 'rgba(232,238,240,.55)'
    if (focus !== 0 && focus !== 3)
      ctx.fillText(
        tr(
          'Detections per week (UTC) · dashed bars: incomplete week',
          'Detecciones por semana (UTC) · barras punteadas: semana incompleta',
        ),
        x0 + width,
        base - 52,
      )
    // Annotations for the active indicator on the timeline itself.
    ctx.font = "600 11px 'IBM Plex Sans', Arial, sans-serif"
    ctx.textBaseline = 'bottom'
    ctx.fillStyle = '#ffb08f'
    ctx.strokeStyle = 'rgba(255,176,143,.8)'
    if (focus === 0 && season.length) {
      const a = x0 + season[0] * bw,
        b = x0 + (season[season.length - 1] + 1) * bw,
        y = base - 40
      ctx.beginPath()
      ctx.moveTo(a, y + 4)
      ctx.lineTo(a, y)
      ctx.lineTo(b, y)
      ctx.lineTo(b, y + 4)
      ctx.stroke()
      ctx.textAlign = 'center'
      ctx.fillText(tr('July → October', 'julio → octubre'), (a + b) / 2, y - 3)
    } else if (focus === 3) {
      const yMed = base - (weeks[medianIndex].count / peak) * 34
      ctx.setLineDash([3, 4])
      ctx.beginPath()
      ctx.moveTo(x0, yMed)
      ctx.lineTo(x0 + width, yMed)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.textAlign = 'left'
      ctx.fillText(
        `${tr('typical week', 'semana típica')} · ${fmt.format(weeks[medianIndex].count)}`,
        x0,
        yMed - 3,
      )
      ctx.textAlign = 'center'
      ctx.fillText(
        `${tr('peak', 'pico')} · ${fmt.format(weeks[peakIndex].count)}`,
        x0 + (peakIndex + 0.5) * bw,
        base - 37,
      )
    }
    ctx.restore()
  }

  // The mouse wheel moves in jumps (~100 px); the scene chases the scroll with exponential damping
  // so the transition stays continuous even when the scroll is not.
  const FLARES = 25,
    flares: { i: number; born: number; life: number; r: number }[] = []
  let frame = 0,
    last = performance.now(),
    clock = 0,
    morph = -1,
    fire = 0,
    dim = 0,
    stage = 0,
    regionT = 0
  function draw(now: number) {
    const dt = Math.min(0.1, (now - last) / 1000),
      animate = true
    last = now
    clock += dt
    const target = hooks.progress()
    if (morph < 0) ({ morph, fire, dim, stage } = target)
    else {
      const k = 1 - Math.exp(-dt * 6)
      morph += (target.morph - morph) * k
      fire += (target.fire - fire) * k
      dim += (target.dim - dim) * k
      stage += (target.stage - stage) * k
    }
    regionT += ((target.focus === 2 ? 1 : 0) - regionT) * (1 - Math.exp(-dt * 5))
    if (target.focus !== focus) {
      focus = target.focus
      if (focus >= 0) weekFloat = 0
    }
    const viewT = ease(clamp(morph * 1.12)),
      view = mix(mix(worldView, peruView, viewT), centerView, ease(clamp(stage)))
    const X = (lon: number) => view.sx + (lon - view.cx) * view.k,
      Y = (lat: number) => view.sy - (lat - view.cy) * view.k
    ctx.clearRect(0, 0, W, H)
    ctx.globalAlpha = 1 - dim * 0.72

    // Polvo de fondo.
    ctx.fillStyle = 'rgba(205,218,232,1)'
    for (const d of dust) {
      const x = X(d.x),
        y = Y(d.y)
      if (x < 0 || y < 0 || x > W || y > H) continue
      ctx.globalAlpha = d.a * (1 - dim * 0.72)
      ctx.fillRect(x, y, 1, 1)
    }
    ctx.globalAlpha = 1 - dim * 0.72

    // Particles grouped in color/opacity buckets for few fillStyle changes. They are drawn with fillRect, not
    // rect()+fill(): mid-morph uses ~130 buckets and each path fill rasterizes a full-screen path, which took
    // ~87 ms/frame on a CPU-rasterized canvas (fillRect: ~6 ms). Measure with web/scripts/perf-scene.js.
    bucketSize.fill(0)
    for (let i = 0; i < LAND; i++) {
      const t = ease(clamp((morph - delay[i]) / 0.55))
      let lon = ax[i] + (bx[i] - ax[i]) * t,
        lat = ay[i] + (by[i] - ay[i]) * t
      if (t > 0 && t < 1) {
        const dx = bx[i] - ax[i],
          dy = by[i] - ay[i],
          bend = Math.sin(Math.PI * t) * arc[i]
        lon -= dy * bend
        lat += dx * bend
      }
      // Float in pixels (not degrees): slight on the planet, wider once suspended on the perimeter.
      const wob = (0.8 + t * (edge[i] ? 5.2 : 2.6)) * WOBBLE,
        w = clock * freq[i] + phase[i]
      sx[i] = X(lon) + Math.sin(w) * wob
      sy[i] = Y(lat) + Math.cos(w * 0.83 + phase[i]) * wob
      const b =
        (((peruA[i] << 1) | edge[i]) * 9 + Math.round(t * 8)) * 8 +
        Math.min(7, Math.floor(alpha[i] * 8))
      bucketOf[i] = b
      bucketSize[b]++
    }
    bucketStart[0] = 0
    for (let b = 0; b < bucketCount; b++) bucketStart[b + 1] = bucketStart[b] + bucketSize[b]
    const cursor = bucketStart.slice(0, bucketCount)
    for (let i = 0; i < LAND; i++) sorted[cursor[bucketOf[i]]++] = i
    for (let b = 0; b < bucketCount; b++) {
      if (!bucketSize[b]) continue
      ctx.fillStyle = styleFor(b)
      for (let n = bucketStart[b]; n < bucketStart[b + 1]; n++) {
        const i = sorted[n],
          x = sx[i],
          y = sy[i]
        if (x < -4 || y < -4 || x > W + 4 || y > H + 4) continue
        ctx.fillRect(x, y, size[i], size[i])
      }
    }

    // Planet flares: up to FLARES land particles light up for 2–4 s and fade out; they disappear as the morph advances.
    const flareFade = clamp(1 - morph * 2.2)
    if (flareFade > 0) {
      if (flares.length < FLARES && Math.random() < dt * 9) {
        const i = Math.floor(Math.random() * LAND)
        if (!peruA[i])
          flares.push({
            i,
            born: clock,
            life: 2 + Math.random() * 2,
            r: 5 + Math.random() * 9,
          })
      }
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'
      for (let n = flares.length - 1; n >= 0; n--) {
        const f = flares[n],
          t = (clock - f.born) / f.life
        if (t >= 1) {
          flares.splice(n, 1)
          continue
        }
        ctx.globalAlpha = flareFade * (1 - dim * 0.72) * Math.sin(Math.PI * t) ** 2 * 0.9
        const r = f.r * (0.7 + 0.3 * Math.sin(Math.PI * t))
        ctx.drawImage(sprite, sx[f.i] - r, sy[f.i] - r, r * 2, r * 2)
      }
      ctx.restore()
    } else flares.length = 0

    // Weekly hotspots: intensity is interpolated between consecutive weeks.
    if (fire > 0 && weeks.length) {
      // With an active indicator the animation walks only its weeks (e.g. alternates typical week ↔ peak).
      const seq = focus >= 0 && sequences[focus].length ? sequences[focus] : all,
        slow = focus === 3 ? 2.2 : 1
      if (animate) weekFloat = (weekFloat + dt / (WEEK_SECONDS * slow)) % seq.length
      const k0 = Math.floor(weekFloat) % seq.length,
        w0 = seq[k0],
        w1 = seq[(k0 + 1) % seq.length]
      const f = smooth(weekFloat - Math.floor(weekFloat))
      current = w0
      ctx.save()
      ctx.globalCompositeOperation = 'lighter'
      const cellPx = (data?.cell_degrees ?? 0.1) * view.k
      for (let c = 0; c < series.length; c++) {
        const n = series[c][w0] + (series[c][w1] - series[c][w0]) * f
        if (n < 0.05) continue
        const r = Math.min(26, (2.2 + Math.sqrt(n) * 2.1) * Math.max(0.7, cellPx / 4))
        ctx.globalAlpha =
          fire *
          (1 - dim * 0.72) *
          Math.min(1, 0.3 + 0.22 * Math.sqrt(n)) *
          (cellRegion[c] ? 1 + regionT * 0.3 : 1 - regionT * 0.75)
        ctx.drawImage(sprite, X(cellLon[c]) - r, Y(cellLat[c]) - r, r * 2, r * 2)
      }
      ctx.restore()
      if (w0 !== lastWeek) {
        lastWeek = w0
        hooks.onWeek(weeks[w0], w0)
      }
      // Priority regions: outline and name of the three departments with the most detections.
      if (regionT > 0.02) {
        ctx.save()
        ctx.globalAlpha = regionT * (1 - dim)
        ctx.strokeStyle = '#ff6a3d'
        ctx.lineWidth = 1.4
        ctx.fillStyle = '#ffd2bf'
        ctx.font = "600 12px 'IBM Plex Sans', Arial, sans-serif"
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        for (const r of regions) {
          let cx = 0,
            cy = 0,
            n = 0
          ctx.beginPath()
          for (const ring of r.rings)
            ring.forEach(([lon, lat], i) => {
              const x = X(lon),
                y = Y(lat)
              if (i) ctx.lineTo(x, y)
              else ctx.moveTo(x, y)
              cx += x
              cy += y
              n++
            })
          ctx.stroke()
          ctx.fillText(r.name, cx / n, cy / n)
        }
        ctx.restore()
      }
    }
    axes(view, (1 - dim * 0.6) * (1 - stage * 0.5), fire * (1 - dim))
    frame = requestAnimationFrame(draw)
  }
  frame = requestAnimationFrame(draw)
  return {
    destroy() {
      cancelAnimationFrame(frame)
      observer.disconnect()
    },
  }
}
