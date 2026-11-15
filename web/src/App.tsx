import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  Download,
  Globe2,
  Info,
  Layers2,
  MapPin,
  MessageSquareText,
  Share2,
  Sparkles,
  X,
  Check,
  SlidersHorizontal,
  Compass,
  CircleHelp,
  UserRound,
} from 'lucide-react'
import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import Account from './Account'
import {
  api,
  post,
  fmt,
  months,
  shortMonths,
  SOURCES,
  sourceName,
  translatedName,
  pct,
  HARMONIZED,
  harmonizedName,
  fromHarmonized,
  pointsFromHarmonized,
} from './api'
import Calendar from './Calendar'
import DataPanel from './DataPanel'
import Dialog from './Dialog'
import Experiment from './Experiment'
import ExperimentalTag from './ExperimentalTag'
import AnalystPanel from './AnalystPanel'
import { DAY_COLORS, DAY_RANGES } from './dayColors'
import { tr, locale, getLang } from './i18n'
import LangSwitch from './LangSwitch'
import Priority from './Priority'
import ReportButton from './ReportButton'
import Tour from './Tour'
import type {
  AnalystAction,
  Analysis,
  Catalog,
  Comparison,
  Geometry,
  HarmonizedAnalysis,
  HarmonizedPoints,
  Health,
  Job,
  Layer,
  Places,
  Point,
  Points,
  Regions,
  Selection,
  Readiness,
  ReportRequest,
  Status,
  User,
} from './types'
const Globe = lazy(() => import('./Globe'))
export type Tab = 'atlas' | 'calendar' | 'priority' | 'lab' | 'data'
export type Modal = '' | 'evidence' | 'export' | 'explain' | 'area'
const NOW = new Date()
// The example of the challenge video (CONAE activation ACT#356): the fire of Chilecito, La Rioja, Argentina,
// July 2026, around Guanchín in the Famatina range.
const CHILECITO: Geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [-67.75, -29.35],
      [-67.05, -29.35],
      [-67.05, -28.75],
      [-67.75, -28.75],
      [-67.75, -29.35],
    ],
  ],
}
const DEFAULT: Selection = {
  scope: 'PER', // Peru by default: the world analysis (~2.5 s + 2.8 MB of points) loads only when picked
  area_label: '',
  department: 'all',
  source: 'viirs-jpss1',
  platform: 'all',
  year_start: 2025,
  year_end: 2026,
  selected_year: 2026,
  selected_month: 7,
  metric: 'observed',
  daynight: 'all',
  fire_type: 'all',
  geometry: null,
}
function readLink() {
  try {
    const raw = new URLSearchParams(location.search).get('s')
    if (raw) {
      const value = JSON.parse(raw)
      return {
        selection: { ...DEFAULT, ...value.selection } as Selection,
        place: String(value.place || 'PER'),
        tab: (['atlas', 'calendar', 'priority', 'lab', 'data'].includes(value.tab)
          ? value.tab
          : 'atlas') as Tab,
        linked: true,
      }
    }
  } catch {
    /* invalid shared link: fall back to the defaults */
  }
  return {
    selection: DEFAULT,
    place: 'PER',
    tab: 'atlas' as Tab,
    linked: false,
  }
}
const linked = readLink()
export default function App() {
  const [selection, setSelection] = useState<Selection>(linked.selection),
    [placeId, setPlaceId] = useState(linked.place),
    [tab, setTab] = useState<Tab>(linked.tab),
    [places, setPlaces] = useState<Places | null>(null),
    [regions, setRegions] = useState<Regions | null>(null),
    [status, setStatus] = useState<Status | null>(null),
    [catalog, setCatalog] = useState<Catalog | null>(null),
    [health, setHealth] = useState<Health | null>(null),
    [jobs, setJobs] = useState<Job[]>([])
  const [analysis, setAnalysis] = useState<Analysis | null>(null),
    [points, setPoints] = useState<Points | null>(null),
    [comparison, setComparison] = useState<Comparison | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [modal, setModal] = useState<Modal>(''),
    [intro, setIntro] = useState(!linked.linked),
    [drawing, setDrawing] = useState(false),
    [flat, setFlat] = useState(false),
    [split, setSplit] = useState(50),
    [inspected, setInspected] = useState<Point | null>(null),
    [viirs, setViirs] = useState('viirs-snpp'),
    [extraFilters, setExtraFilters] = useState(false),
    [tour, setTour] = useState(false),
    // Atlas points: by sensor, or by day of the last detection in the month (FIRMS "time since detection").
    [colorBy, setColorBy] = useState<'sensor' | 'day'>('day'),
    // The analyst is a side panel: the map stays visible and its buttons act on it; the conversation
    // survives closing the panel because the panel stays mounted.
    [analystOpen, setAnalystOpen] = useState(false)
  const [user, setUser] = useState<User | null>(null),
    [accountOpen, setAccountOpen] = useState(false),
    [readiness, setReadiness] = useState<Readiness | null>(null),
    [harmonized, setHarmonized] = useState<HarmonizedAnalysis | null>(null),
    [labLayers, setLabLayers] = useState<Layer[] | null>(null),
    [observer, setObserver] = useState('')
  const isHarmonized = selection.source === HARMONIZED
  function change(patch: Partial<Selection>) {
    setSelection((previous) => ({ ...previous, ...patch }))
    setInspected(null)
    setIntro(false)
  }
  async function refresh() {
    try {
      const [s, h, j, c] = await Promise.all([
        api<Status>('/status'),
        api<Health>('/health'),
        api<Job[]>('/jobs'),
        api<Catalog>('/catalog'),
      ])
      setStatus(s)
      setHealth(h)
      setJobs(j)
      setCatalog(c)
    } catch (e) {
      setError(String(e))
    }
  }
  useEffect(() => {
    api<Places>('/places')
      .then(setPlaces)
      .catch((e) => setError(e.message))
    api<Regions>('/regions')
      .then(setRegions)
      .catch((e) => setError(e.message))
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
    api<Readiness>('/harmonization')
      .then(setReadiness)
      .catch(() => setReadiness(null))
    refresh()
  }, [])
  // First visit (no shared link): open on the harmonized record, the sensor-independent calendar,
  // instead of a single instrument. A shared link keeps whatever it carries.
  const openedHarmonized = useRef(linked.linked)
  useEffect(() => {
    if (!readiness?.available || openedHarmonized.current || selection.scope === 'world') return
    openedHarmonized.current = true
    change({ source: HARMONIZED, platform: 'all', metric: 'observed', year_start: 2002 })
  }, [readiness?.available])
  useEffect(() => {
    if (
      !places ||
      selection.scope !== 'custom' ||
      selection.geometry ||
      !placeId.startsWith('country:')
    )
      return
    const country = places.features.find((p) => p.properties.id === placeId.slice(8))
    if (country) setSelection((s) => ({ ...s, geometry: country.geometry }))
  }, [places])
  const dataRevision = status?.batches.map((b) => b.id).join(',')
  // The first revision to arrive (/status takes ~1.3 s) is the data the first analysis already reads:
  // only a later change restarts it, so the opening request is not aborted and sent again.
  const firstRevision = useRef(dataRevision)
  if (firstRevision.current === undefined) firstRevision.current = dataRevision
  const revisionKey = dataRevision === firstRevision.current ? 'initial' : dataRevision
  useEffect(() => {
    if (selection.scope === 'custom' && !selection.geometry) return
    const abort = new AbortController()
    setLoading(true)
    setAnalysis(null)
    setPoints(null)
    setComparison(null)
    setInspected(null)
    setHarmonized(null)
    const request = isHarmonized
      ? post<HarmonizedAnalysis>('/harmonized/analyses', harmonizedBody(), abort.signal).then(
          (h) => {
            if (!abort.signal.aborted) setHarmonized(h)
            return fromHarmonized(h, selection, placeLabel)
          },
        )
      : post<Analysis>('/analyses', selection, abort.signal)
    request
      .then((a) => {
        if (!abort.signal.aborted) setAnalysis(a)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false)
      })
    return () => abort.abort()
  }, [JSON.stringify(selection), revisionKey, isHarmonized && !!regions && !!places])
  useEffect(() => {
    if (!analysis) return
    const abort = new AbortController()
    const { selected_year, selected_month } = analysis.selection
    const date = `${selected_year}-${String(selected_month).padStart(2, '0')}`
    const request = isHarmonized
      ? api<HarmonizedPoints>(`/harmonized/analyses/${analysis.id}/points?limit=5000`, {
          signal: abort.signal,
        }).then((p) => pointsFromHarmonized(p, date))
      : api<Points>(`/analyses/${analysis.id}/points`, { signal: abort.signal })
    request.then(setPoints).catch((e) => {
      if (e.name !== 'AbortError') setError(e.message)
    })
    return () => abort.abort()
  }, [analysis?.id])
  useEffect(() => {
    // Without a harmonized product the lab falls back to comparing two sensors.
    if (!analysis || tab !== 'lab' || isHarmonized || readiness?.available) return
    const abort = new AbortController()
    setComparison(null)
    api<Comparison>(`/analyses/${analysis.id}/comparison?viirs=${viirs}`, {
      signal: abort.signal,
    })
      .then(setComparison)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => abort.abort()
  }, [analysis?.id, tab, viirs])
  // Lab: the harmonized series (left) against the original observations of one sensor (right).
  const observed =
    observer ||
    (selection.source !== HARMONIZED
      ? `${selection.source}:${selection.platform}`
      : selection.scope === 'world'
        ? 'viirs-jpss1:all'
        : 'modis:Aqua')
  useEffect(() => {
    if (tab !== 'lab' || !readiness?.available) return
    if (selection.scope === 'custom' && !selection.geometry) return
    const abort = new AbortController()
    const { signal } = abort
    const [source, platform] = observed.split(':')
    const date = `${selection.selected_year}-${String(selection.selected_month).padStart(2, '0')}`
    setLabLayers(null)
    const left = post<HarmonizedAnalysis>('/harmonized/analyses', harmonizedBody(), signal).then(
      (h) =>
        api<HarmonizedPoints>(`/harmonized/analyses/${h.id}/points?limit=5000`, { signal }).then(
          (p) => ({
            source: HARMONIZED,
            platform: 'all',
            selected: fromHarmonized(h, selection, placeLabel).selected,
            points: pointsFromHarmonized(p, date),
            analysis_id: h.id,
          }),
        ),
    )
    const right = post<Analysis>(
      '/analyses',
      { ...selection, source, platform, metric: 'observed' },
      signal,
    ).then((a) =>
      api<Points>(`/analyses/${a.id}/points`, { signal }).then((points) => ({
        source,
        platform,
        selected: a.selected,
        points,
        analysis_id: a.id,
      })),
    )
    Promise.all([left, right])
      .then((layers) => {
        if (!signal.aborted) setLabLayers(layers)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => abort.abort()
  }, [tab, readiness?.available, JSON.stringify(selection), observed, !!regions && !!places])
  useEffect(() => {
    if (!jobs.some((j) => ['queued', 'running'].includes(j.status))) return
    const interval = setInterval(refresh, 1800)
    return () => clearInterval(interval)
  }, [JSON.stringify(jobs)])
  useEffect(() => {
    const geometry = placeId.startsWith('country:') ? null : selection.geometry
    const url = new URL(location.href)
    url.searchParams.set(
      's',
      JSON.stringify({
        selection: { ...selection, geometry },
        place: placeId,
        tab,
      }),
    )
    history.replaceState(null, '', url)
  }, [JSON.stringify(selection), placeId, tab])
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(''), 8000)
    return () => clearTimeout(timer)
  }, [notice])
  const MONTHS = months(),
    SHORT = shortMonths()
  const country = places?.features.find((p) => `country:${p.properties.id}` === placeId) || null
  const department =
    regions?.geojson.features.find((p) => p.properties.id === selection.department) || null
  const currentPlace =
    department ||
    country ||
    (selection.scope === 'PER'
      ? places?.features.find((p) => p.properties.name === 'Peru') || null
      : null)
  // Name of the chosen place without an analysis (the harmonized API does not return one).
  const placeLabel =
    placeId === 'world'
      ? tr('The planet', 'El planeta')
      : placeId === 'PER'
        ? tr('All of Peru', 'Perú completo')
        : department
          ? department.properties.name
          : country
            ? translatedName(country.properties.name)
            : selection.area_label || tr('Your selection', 'Tu selección')
  // The UI names the place itself so the name follows the interface language.
  const label = placeLabel
  // Peru and its regions query Peru (a region by its outline); a country by name; a drawn area worldwide.
  function harmonizedBody() {
    return {
      country: selection.scope === 'PER' ? 'Peru' : country ? country.properties.name : 'world',
      year_start: selection.year_start,
      year_end: selection.year_end,
      selected_year: selection.selected_year,
      selected_month: selection.selected_month,
      geometry:
        selection.scope === 'PER'
          ? department?.geometry || null
          : country
            ? null
            : selection.geometry,
    }
  }
  // Territorial report of what is on screen: Peru, one of its regions, another country or a drawn
  // area; the planet as a whole has no long history to compare with.
  function reportBody(): ReportRequest | null {
    if (selection.scope === 'world') return null
    return {
      country: selection.scope === 'PER' ? 'Peru' : country ? country.properties.name : 'world',
      place_name: department
        ? department.properties.name
        : selection.scope === 'custom'
          ? selection.area_label || null
          : null,
      geometry:
        selection.scope === 'PER' ? department?.geometry || null : country ? null : selection.geometry,
      year: selection.selected_year,
      month: selection.selected_month,
      language: getLang(),
    }
  }
  function choosePlace(id: string) {
    const worldPeriod =
      selection.selected_year < 2025 ||
      (selection.selected_year === 2025 && selection.selected_month < 11)
        ? {
            year_start: 2025,
            year_end: 2026,
            selected_year: 2026,
            selected_month: 7,
          }
        : {}
    setPlaceId(id)
    setError('')
    setIntro(false)
    if (id === 'world') {
      change({
        ...worldPeriod,
        scope: 'world',
        department: 'all',
        geometry: null,
        area_label: '',
        metric: 'observed',
      })
      return
    }
    if (id === 'PER') {
      change({
        scope: 'PER',
        department: 'all',
        geometry: null,
        area_label: '',
        metric: 'observed',
        selected_year: 2025,
        selected_month: 9,
        year_end: 2025,
        ...(isHarmonized ? { year_start: 2002 } : { year_start: 2018, source: 'modis', platform: 'Aqua' }),
      })
      return
    }
    if (id === 'case:chilecito') {
      setPlaceId('custom')
      change({
        scope: 'custom',
        area_label: 'Chilecito, La Rioja (Argentina)',
        geometry: CHILECITO,
        department: 'all',
        metric: 'observed',
        selected_year: 2026,
        selected_month: 7,
        year_start: 2002,
        year_end: 2026,
        ...(readiness?.available ? { source: HARMONIZED, platform: 'all' } : {}),
      })
      return
    }
    if (id.startsWith('region:')) {
      const chosen = regions?.geojson.features.find((f) => f.properties.id === id.slice(7))
      if (chosen)
        change({
          scope: 'PER',
          department: chosen.properties.id,
          geometry: null,
          area_label: '',
          metric: 'observed',
        })
      return
    }
    const chosen = places?.features.find((p) => `country:${p.properties.id}` === id)
    if (chosen)
      change({
        ...worldPeriod,
        scope: 'custom',
        area_label: translatedName(chosen.properties.name),
        geometry: chosen.geometry,
        department: 'all',
        metric: 'observed',
      })
  }
  // A button offered by the analyst: select the territory and period, keep the current data source
  // (the analyst lives in the harmonized view) and show the requested view.
  function runAnalystAction(action: AnalystAction) {
    const fold = (text: string) =>
      text
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '')
        .toUpperCase()
        .trim()
    const keep = { source: selection.source, platform: selection.platform }
    if (action.kind !== 'open_priorities' && action.country) {
      if (action.country === 'Peru') {
        const region = action.department
          ? regions?.geojson.features.find((f) => fold(f.properties.name) === fold(action.department ?? ''))
          : undefined
        choosePlace(region ? `region:${region.properties.id}` : 'PER')
      } else {
        const place = places?.features.find((p) => p.properties.name === action.country)
        if (!place) {
          setError(tr(`${action.country} is not available on the map.`, `${action.country} no está disponible en el mapa.`))
          return
        }
        choosePlace(`country:${place.properties.id}`)
      }
    }
    if (action.year && action.month) {
      const year = action.year
      change({
        ...keep,
        selected_year: year,
        selected_month: action.month,
        year_start: Math.min(selection.year_start, year),
        year_end: Math.max(selection.year_end, year),
      })
    } else change(keep)
    setTab(action.kind === 'open_calendar' ? 'calendar' : action.kind === 'open_priorities' ? 'priority' : 'atlas')
  }
  function applyGeometry(geometry: Geometry) {
    setPlaceId('custom')
    change({
      scope: 'custom',
      department: 'all',
      geometry,
      area_label: tr('Custom area', 'Área personalizada'),
      metric: 'observed',
    })
    setDrawing(false)
    setModal('')
  }
  // The analyst answers about the harmonized record: switch to it when it is available, then open the panel.
  function openAnalyst() {
    if (!isHarmonized && readiness?.available && selection.scope !== 'world') selectSource(`${HARMONIZED}:all`)
    setIntro(false)
    setModal('')
    setAnalystOpen(true)
  }
  function selectSource(value: string) {
    const [source, platform] = value.split(':')
    // The harmonized series starts in 2002 (Terra-only months are not served); the world archive covers recent years.
    if (source === HARMONIZED && selection.scope !== 'world') {
      change({ source, platform, metric: 'observed', year_start: 2002 })
      return
    }
    change({ source, platform, metric: 'observed' })
    if (source.startsWith('viirs')) setViirs(source)
  }
  async function share() {
    try {
      await navigator.clipboard.writeText(location.href)
      setNotice(
        tr(
          'Link copied with the territory, period and analysis settings.',
          'Enlace copiado con el territorio, período y configuración del análisis.',
        ),
      )
    } catch {
      setNotice(
        tr(
          'You can copy the browser address: it keeps the current selection.',
          'Puedes copiar la dirección del navegador: conserva la selección actual.',
        ),
      )
    }
  }
  function startTour() {
    setIntro(false)
    setExtraFilters(false)
    setDrawing(false)
    setTab('atlas')
    window.scrollTo({ top: 0, behavior: 'instant' })
    setTour(true)
  }
  // Dragging the divider icon reveals one observer or the other (the range slider stays available).
  function dragSeam(e: ReactPointerEvent<HTMLButtonElement>) {
    const stage = e.currentTarget.closest('.atlas-stage')
    if (!stage) return
    e.preventDefault()
    const rect = stage.getBoundingClientRect()
    const move = (ev: PointerEvent) =>
      setSplit(Math.round(Math.min(95, Math.max(5, ((ev.clientX - rect.left) / rect.width) * 100))))
    const up = () => {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }
  const selected = analysis?.selected
  const layers: Layer[] =
    tab === 'lab'
      ? (readiness?.available ? labLayers : comparison?.layers) || []
      : analysis && points
        ? [
            {
              source: selection.source,
              platform: selection.platform,
              selected: analysis.selected,
              points,
              analysis_id: analysis.id,
            },
          ]
        : []
  const labHarmonized = !!readiness?.available,
    labReady = labHarmonized ? !!labLayers : !!comparison
  const displayed = layers.reduce((sum, l) => sum + l.points.shown, 0),
    total = layers.reduce((sum, l) => sum + l.points.total, 0)
  const firstYear =
    isHarmonized && selection.scope !== 'world' ? 2002 : selection.scope === 'PER' ? 2000 : 2025
  const years = Array.from(
    {
      length: Math.max(NOW.getUTCFullYear(), selection.year_end) - firstYear + 1,
    },
    (_, i) => firstYear + i,
  ).reverse()
  const lastGlobal = (status?.batches.filter((b) => b.spatial_scope === 'world') || []).reduce(
    (latest, b) => (b.coverage_end > latest ? b.coverage_end : latest),
    '',
  )
  const firstGlobal = (
    status?.batches.filter((b) => b.spatial_scope === 'world' && b.coverage_start) || []
  ).reduce((first, b) => (!first || b.coverage_start < first ? b.coverage_start : first), '')
  const date = `${selection.selected_year}-${String(selection.selected_month).padStart(2, '0')}`
  const shownWindow =
    analysis?.archive_windows.filter(
      (w) => w.start.slice(0, 7) <= date && w.end.slice(0, 7) >= date,
    ) || []
  const monthName = MONTHS[selection.selected_month - 1]
  const noData = tr('No data available', 'Sin datos disponibles')
  return (
    <div className="nina-app">
      <a className="skip-link" href="#main">
        {tr('Skip to content', 'Ir al contenido')}
      </a>
      <header className="site-header">
        <a
          href="/"
          className="brand"
          onClick={(e) => {
            e.preventDefault()
            // Back to the landing (main.tsx listens to hashchange); Back returns to the atlas.
            history.pushState(null, '', location.pathname)
            dispatchEvent(new HashChangeEvent('hashchange'))
          }}
          aria-label={tr('NINA, go to the home page', 'NINA, ir a la página de inicio')}
        >
          NINA
          <span>{tr('The memory of fire', 'La memoria del fuego')}</span>
        </a>
        <nav aria-label={tr('Investigation views', 'Vistas de la investigación')}>
          {[
            ['atlas', 'Atlas'],
            ['calendar', tr('Calendar', 'Calendario')],
            ['priority', tr('Priorities', 'Prioridades')],
            ['lab', tr('Lab', 'Laboratorio')],
          ].map(([id, name]) => (
            <button
              key={id}
              aria-current={tab === id ? 'page' : undefined}
              onClick={() => {
                setTab(id as Tab)
                if (id === 'lab' && selection.source.startsWith('viirs')) setViirs(selection.source)
              }}
            >
              {name}
            </button>
          ))}
        </nav>
        <div className="header-actions">
          <button className="ask-nina" onClick={openAnalyst}>
            <Sparkles size={16} />
            <span>{tr('Ask NINA', 'Pregúntale a NINA')}</span>
          </button>
          <LangSwitch />
          <button
            className="tour-start"
            onClick={startTour}
            aria-label={tr('Platform guide', 'Guía de la plataforma')}
          >
            <CircleHelp size={16} />
            <span>{tr('Guide', 'Guía')}</span>
          </button>
          <button className={tab === 'data' ? 'active' : ''} onClick={() => setTab('data')}>
            <BookOpen size={17} />
            <span>{tr('Sources', 'Fuentes')}</span>
          </button>
          <button
            onClick={() => setAccountOpen(true)}
            aria-label={
              user
                ? tr(`Account for ${user.email}`, `Cuenta de ${user.email}`)
                : tr('Sign in to NINA', 'Entrar en NINA')
            }
          >
            <UserRound size={17} />
            <span>
              {user ? user.display_name || user.email.split('@')[0] : tr('Sign in', 'Entrar')}
            </span>
          </button>
          <button
            onClick={share}
            aria-label={tr('Share this investigation', 'Compartir esta investigación')}
          >
            <Share2 size={17} />
          </button>
        </div>
      </header>
      <div
        className="selection-bar"
        aria-label={tr('Shared investigation context', 'Contexto compartido de la investigación')}
      >
        <label className="territory-field">
          <MapPin size={16} />
          <span className="sr-only">{tr('Territory', 'Territorio')}</span>
          <select
            aria-label={tr('Territory', 'Territorio')}
            value={placeId}
            onChange={(e) => choosePlace(e.target.value)}
          >
            <option value="world">{tr('The planet', 'El planeta')}</option>
            <option value="PER">
              {tr('Peru · historical archive', 'Perú · archivo histórico')}
            </option>
            <option value="case:chilecito">
              {tr(
                'Challenge example · Chilecito, Argentina (Jul 2026)',
                'Ejemplo del reto · Chilecito, Argentina (jul 2026)',
              )}
            </option>
            {placeId === 'custom' && (
              <option value="custom">{tr('Custom area', 'Área personalizada')}</option>
            )}
            <optgroup
              label={tr('Countries · reference cartography', 'Países · cartografía de referencia')}
            >
              {places?.features
                .filter((p) => p.properties.name !== 'Peru')
                .sort((a, b) =>
                  translatedName(a.properties.name).localeCompare(
                    translatedName(b.properties.name),
                    locale(),
                  ),
                )
                .map((p) => (
                  <option key={p.properties.id} value={`country:${p.properties.id}`}>
                    {translatedName(p.properties.name)}
                  </option>
                ))}
            </optgroup>
            {regions && (
              <optgroup
                label={tr('Regions of the Peruvian archive', 'Regiones del archivo peruano')}
              >
                {regions.geojson.features.map((p) => (
                  <option key={p.properties.id} value={`region:${p.properties.id}`}>
                    {p.properties.name} · {tr('Peru', 'Perú')}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
          <ChevronDown size={14} />
        </label>
        <label className="sensor-field">
          <span>{tr('Observer', 'Observador')}</span>
          <select
            aria-label={tr('Observer', 'Observador')}
            value={`${selection.source}:${selection.platform}`}
            onChange={(e) => selectSource(e.target.value)}
          >
            <optgroup label={tr('Original observations', 'Observaciones originales')}>
              {SOURCES.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </optgroup>
            {(readiness?.available || isHarmonized) && (
              <optgroup label={tr('Processed product', 'Producto procesado')}>
                <option value={`${HARMONIZED}:all`}>{harmonizedName()}</option>
              </optgroup>
            )}
          </select>
        </label>
        <div className="selection-meta">
          <span className="status-dot" />
          {selection.scope === 'PER'
            ? tr('History 2000–2025, by product', 'Histórico 2000–2025, según producto')
            : lastGlobal
              ? `${tr('Global archive', 'Archivo mundial')} · ${firstGlobal} → ${lastGlobal}`
              : tr('Global exploration · query by area', 'Exploración mundial · consulta por área')}
        </div>
        <button
          className="filter-button"
          aria-expanded={extraFilters}
          onClick={() => setExtraFilters(!extraFilters)}
        >
          <SlidersHorizontal size={16} />
          <span>{tr('Filters', 'Filtros')}</span>
        </button>
      </div>
      {extraFilters && (
        <div className="advanced-filters">
          <button className="coordinates-button" onClick={() => setModal('area')}>
            <Compass size={16} />
            <span>{tr('Area by coordinates', 'Área por coordenadas')}</span>
          </button>
          <label>
            {tr('Time of day', 'Horario')}
            <select
              value={selection.daynight}
              onChange={(e) => change({ daynight: e.target.value })}
            >
              <option value="all">{tr('Day and night', 'Día y noche')}</option>
              <option value="D">{tr('Day', 'Día')}</option>
              <option value="N">{tr('Night', 'Noche')}</option>
            </select>
          </label>
          <label>
            {tr('Type', 'Tipo')}
            <select
              value={selection.fire_type}
              onChange={(e) => change({ fire_type: e.target.value })}
            >
              <option value="all">{tr('All detections', 'Todas las detecciones')}</option>
              <option value="vegetation">{tr('Vegetation type', 'Tipo vegetación')}</option>
            </select>
          </label>
          <span>
            {tr(
              'The type depends on the product; a missing type is not classified as vegetation.',
              'El tipo depende del producto; una ausencia no se clasifica como vegetación.',
            )}
          </span>
          <button
            onClick={() => setExtraFilters(false)}
            aria-label={tr('Close filters', 'Cerrar filtros')}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          <Info size={17} />
          <span>{error}</span>
          <button onClick={() => setError('')} aria-label={tr('Close message', 'Cerrar mensaje')}>
            <X size={17} />
          </button>
        </div>
      )}
      {notice && (
        <div className="notice-toast" role="status">
          <Check size={17} />
          <span>{notice}</span>
          <button
            aria-label={tr('Close notification', 'Cerrar notificación')}
            onClick={() => setNotice('')}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <main id="main">
        {(tab === 'atlas' || tab === 'lab') && (
          <>
            <section
              className={`atlas-stage ${intro && tab === 'atlas' ? 'has-intro' : ''} ${tab === 'lab' ? 'comparison-stage' : ''}`}
              aria-label={
                tab === 'lab'
                  ? tr('Sensor comparison', 'Comparación de sensores')
                  : tr('World atlas', 'Atlas mundial')
              }
            >
              <Suspense
                fallback={
                  <div className="globe-loading">
                    <Globe2 size={34} />
                    <span>{tr('Preparing the planet…', 'Preparando el planeta…')}</span>
                  </div>
                }
              >
                <Globe
                  colorBy={colorBy}
                  selection={selection}
                  layers={layers}
                  compare={tab === 'lab'}
                  split={split}
                  place={currentPlace}
                  drawing={drawing}
                  onDrawing={setDrawing}
                  onGeometry={applyGeometry}
                  onClear={placeId === 'custom' ? () => choosePlace('world') : undefined}
                  onInspect={setInspected}
                  flat={flat}
                  onFlat={setFlat}
                  busy={loading || (tab === 'lab' ? !labReady : !points)}
                />
              </Suspense>
              {intro && tab === 'atlas' ? (
                <div className="atlas-intro">
                  <span className="map-kicker">
                    {tr('Global archive', 'Archivo mundial')} · 2025–2026
                  </span>
                  <h1>
                    {tr('One story.', 'Una historia.')}
                    <br />
                    {tr('Many', 'Varios')}
                    <br />
                    <em>{tr('observers.', 'observadores.')}</em>
                  </h1>
                  <p>
                    {tr('Walk the fire archive.', 'Recorre el archivo del fuego.')}
                    <br />
                    {tr('Compare what we see.', 'Compara lo que vemos.')}
                    <br />
                    {tr('Check what we know.', 'Comprueba lo que sabemos.')}
                  </p>
                  <button
                    className="button sand"
                    onClick={() => {
                      choosePlace('world')
                      setTab('calendar')
                    }}
                  >
                    {tr('Explore the planet', 'Explorar el planeta')}
                    <ArrowRight size={17} />
                  </button>
                  <button className="intro-secondary" onClick={startTour}>
                    {tr('First time? Platform guide', '¿Primera vez? Guía de la plataforma')}
                    <CircleHelp size={14} />
                  </button>
                  <button
                    className="intro-secondary"
                    onClick={() => {
                      setIntro(false)
                      setModal('area')
                    }}
                  >
                    {tr('Define my area', 'Definir mi área')}
                    <ArrowUpRight size={14} />
                  </button>
                </div>
              ) : (
                tab === 'atlas' && (
                  <div className="map-brief">
                    <span className="map-kicker">
                      {sourceName(selection.source, selection.platform)}
                      {isHarmonized && <ExperimentalTag />}
                    </span>
                    <h1>{label}</h1>
                    <div className="observed-number">
                      {loading ? '…' : fmt(selected?.value)}
                      <span>
                        {isHarmonized
                          ? tr('equivalent active cell-days', 'celdas-día activas equivalentes')
                          : tr('archive detections', 'detecciones del archivo')}
                        <br />
                        {tr(
                          `${monthName} ${selection.selected_year}`,
                          `${monthName.toLowerCase()} de ${selection.selected_year}`,
                        )}
                      </span>
                    </div>
                    <p>
                      {selected?.value == null
                        ? tr(
                            'This period is not available for this selection yet.',
                            'Este período todavía no está disponible para esta selección.',
                          )
                        : selected?.status === 'partial_archive'
                          ? tr(
                              'Partial period. The monthly comparison is omitted.',
                              'Período parcial. La comparación mensual se omite.',
                            )
                          : selected?.historical_median != null
                            ? tr(
                                `${pct(selected.anomaly_percent)} against the median of the same month over ${selected.historical_n} eligible years.`,
                                `${pct(selected.anomaly_percent)} frente a la mediana del mismo mes en ${selected.historical_n} años elegibles.`,
                              )
                            : tr(
                                'The eligible history is not enough for a comparison.',
                                'El historial elegible es insuficiente para una comparación.',
                              )}
                    </p>
                    {shownWindow.length > 0 && selected?.status === 'partial_archive' && (
                      <small>
                        {tr('Loaded window', 'Ventana incorporada')}: {shownWindow[0].start} →{' '}
                        {shownWindow[shownWindow.length - 1].end}
                      </small>
                    )}
                    <div className="brief-actions">
                      <button onClick={() => setTab('calendar')}>
                        {tr('Calendar', 'Calendario')}
                        <ArrowUpRight size={14} />
                      </button>
                      <button onClick={openAnalyst}>
                        <Sparkles size={15} />
                        {tr('Ask NINA', 'Pregúntale a NINA')}
                      </button>
                      <ReportButton body={reportBody()} onError={setError} />
                    </div>
                  </div>
                )
              )}
              {tab === 'lab' && (
                <>
                  <div className="comparison-heading">
                    <span className="map-kicker">
                      {tr('Same territory · same period', 'Mismo territorio · mismo período')}
                    </span>
                    <h1>
                      {labHarmonized
                        ? tr(
                            'One consistent record against a single observer.',
                            'Un registro coherente frente a un solo observador.',
                          )
                        : tr(
                            'The observer changes the signal too.',
                            'El observador también cambia la señal.',
                          )}
                    </h1>
                    <p>
                      {label} · {monthName} {selection.selected_year}
                    </p>
                  </div>
                  <div className="sensor-tag left">
                    <i className={labHarmonized ? 'viirs-circle harmonized-dot' : 'modis-square'} />
                    <span>
                      {labHarmonized ? harmonizedName() : 'MODIS Aqua'}
                      <strong>
                        {layers[0]?.selected.value == null
                          ? noData
                          : fmt(layers[0].selected.value) +
                            ' ' +
                            (labHarmonized
                              ? tr('equivalent cell-days', 'celdas-día equivalentes')
                              : tr('detections', 'detecciones'))}
                      </strong>
                    </span>
                  </div>
                  <div className="sensor-tag right">
                    <i
                      className={
                        (layers[1]?.source === 'modis' ? 'modis-square' : 'viirs-circle') +
                        (labHarmonized ? ' observer-dot' : '')
                      }
                    />
                    <span>
                      {labHarmonized
                        ? sourceName(observed.split(':')[0], observed.split(':')[1])
                        : sourceName(viirs, 'all')}
                      <strong>
                        {layers[1]?.selected.value == null
                          ? noData
                          : fmt(layers[1].selected.value) + ' ' + tr('detections', 'detecciones')}
                      </strong>
                    </span>
                  </div>
                  <div className="comparison-seam" style={{ left: `${split}%` }}>
                    <button
                      type="button"
                      role="slider"
                      aria-label={tr(
                        'Divider between observers: drag or use the arrow keys',
                        'Divisor entre observadores: arrastra o usa las flechas',
                      )}
                      aria-valuemin={5}
                      aria-valuemax={95}
                      aria-valuenow={split}
                      onPointerDown={dragSeam}
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowLeft') {
                          e.preventDefault()
                          setSplit((v) => Math.max(5, v - 2))
                        } else if (e.key === 'ArrowRight') {
                          e.preventDefault()
                          setSplit((v) => Math.min(95, v + 2))
                        }
                      }}
                    >
                      <Layers2 size={16} />
                    </button>
                  </div>
                  <div className="comparison-controls">
                    <label>
                      {tr('Reveal observers', 'Revelar observadores')}
                      <input
                        type="range"
                        min={5}
                        max={95}
                        value={split}
                        aria-label={tr(
                          'Split between MODIS and VIIRS',
                          'División entre MODIS y VIIRS',
                        )}
                        onChange={(e) => setSplit(Number(e.target.value))}
                      />
                    </label>
                    {labHarmonized ? (
                      <select
                        aria-label={tr('Observer to compare', 'Observador de comparación')}
                        value={observed}
                        onChange={(e) => setObserver(e.target.value)}
                      >
                        {SOURCES.map(([id, name]) => (
                          <option key={id} value={id}>
                            {name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <select
                        aria-label={tr('VIIRS to compare', 'VIIRS de comparación')}
                        value={viirs}
                        onChange={(e) => setViirs(e.target.value)}
                      >
                        <option value="viirs-snpp">VIIRS · S-NPP</option>
                        <option value="viirs-jpss1">VIIRS · NOAA-20</option>
                        <option value="viirs-jpss2">VIIRS · NOAA-21</option>
                      </select>
                    )}
                  </div>
                </>
              )}
              {inspected && (
                <aside className="point-inspector">
                  <button
                    className="close-small"
                    onClick={() => setInspected(null)}
                    aria-label={tr('Close observation', 'Cerrar observación')}
                  >
                    <X size={16} />
                  </button>
                  <span className="map-kicker">
                    {inspected.properties.source === HARMONIZED
                      ? tr('One harmonized cell', 'Una celda armonizada')
                      : tr('One archive observation', 'Una observación del archivo')}
                  </span>
                  <h2>{inspected.properties.platform}</h2>
                  {inspected.properties.source === HARMONIZED ? (
                    <>
                      <dl>
                        <dt>{tr('Month', 'Mes')}</dt>
                        <dd>{inspected.properties.date}</dd>
                        <dt>{tr('Cell centre', 'Centro de celda')}</dt>
                        <dd>
                          {inspected.geometry.coordinates.map((n) => n.toFixed(4)).join(', ')}
                        </dd>
                        <dt>{tr('Equivalent activity', 'Actividad equivalente')}</dt>
                        <dd>{fmt(inspected.properties.frp, 2)}</dd>
                        <dt>{tr('Active cell-days', 'Celdas-día activas')}</dt>
                        <dd>{fmt(inspected.properties.scan)}</dd>
                        <dt>{tr('Calibration', 'Calibración')}</dt>
                        <dd>{inspected.properties.confidence}</dd>
                      </dl>
                      <p>
                        {tr(
                          'An H3 cell centre with VIIRS-equivalent activity; not a fire location.',
                          'Centro de una celda H3 con actividad equivalente VIIRS; no es la ubicación de un incendio.',
                        )}
                      </p>
                    </>
                  ) : (
                    <>
                      <dl>
                        <dt>{tr('UTC date', 'Fecha UTC')}</dt>
                        <dd>{inspected.properties.date}</dd>
                        <dt>{tr('Coordinates', 'Coordenadas')}</dt>
                        <dd>
                          {inspected.geometry.coordinates.map((n) => n.toFixed(4)).join(', ')}
                        </dd>
                        <dt>{tr('Fire radiative power', 'Potencia radiativa')}</dt>
                        <dd>{fmt(inspected.properties.frp, 2)} MW</dd>
                        <dt>{tr('Product confidence', 'Confianza del producto')}</dt>
                        <dd>{inspected.properties.confidence}</dd>
                        <dt>{tr('Time of day', 'Horario')}</dt>
                        <dd>
                          {inspected.properties.daynight === 'N'
                            ? tr('Night', 'Noche')
                            : tr('Day', 'Día')}
                        </dd>
                      </dl>
                      <p>
                        {tr(
                          'One detected thermal pixel; it does not identify an individual fire.',
                          'Un píxel térmico detectado; no identifica un incendio individual.',
                        )}
                      </p>
                    </>
                  )}
                </aside>
              )}
              <div className="map-data-note">
                <span>
                  {tab === 'lab' ? (
                    labHarmonized ? (
                      <>
                        <i className="viirs-circle harmonized-dot" />
                        {tr('Harmonized', 'Armonizado')}
                        <i
                          className={
                            (layers[1]?.source === 'modis' ? 'modis-square' : 'viirs-circle') +
                            ' observer-dot'
                          }
                        />
                        {sourceName(observed.split(':')[0], observed.split(':')[1])}
                      </>
                    ) : (
                      <>
                        <i className="modis-square" />
                        MODIS
                        <i className="viirs-circle" />
                        VIIRS
                      </>
                    )
                  ) : (
                    <>
                      <i
                        className={selection.source === 'modis' ? 'modis-square' : 'viirs-circle'}
                      />
                      {sourceName(selection.source, selection.platform)}
                    </>
                  )}
                </span>
                {tab === 'atlas' && (
                  <span className="color-by">
                    {tr('Colour points by', 'Colorear puntos por')}
                    <button aria-pressed={colorBy === 'day'} onClick={() => setColorBy('day')}>
                      {tr('day of detection', 'día de detección')}
                    </button>
                    <button aria-pressed={colorBy === 'sensor'} onClick={() => setColorBy('sensor')}>
                      {tr('sensor', 'sensor')}
                    </button>
                  </span>
                )}
                {tab === 'atlas' && colorBy === 'day' && (
                  <span className="day-legend">
                    <b>
                      {tr(
                        `Last detection in ${monthName} (day of the month):`,
                        `Última detección en ${monthName.toLowerCase()} (día del mes):`,
                      )}
                    </b>
                    {DAY_COLORS.map((rgb, index) => (
                      <span key={rgb}>
                        <i style={{ background: `rgb(${rgb})` }} />
                        {DAY_RANGES[index]}
                      </span>
                    ))}
                  </span>
                )}
                <span>
                  {loading || !points || (tab === 'lab' && !labReady)
                    ? tr('Querying archive points…', 'Consultando puntos del archivo…')
                    : tr(
                        `${fmt(displayed)} of ${fmt(total)} points on screen${displayed < total ? ' · deterministic sample' : ''}`,
                        `${fmt(displayed)} de ${fmt(total)} puntos en pantalla${displayed < total ? ' · muestra determinista' : ''}`,
                      )}
                </span>
              </div>
              {tab === 'atlas' && (
                <button
                  className="map-evidence"
                  disabled={!analysis}
                  onClick={() => setModal('evidence')}
                >
                  <Info size={15} />
                  {tr('Review evidence', 'Revisar evidencia')}
                </button>
              )}
            </section>
            <section className="time-dock" aria-label={tr('Time selection', 'Selección temporal')}>
              <div className="time-title">
                <label>
                  <span>{tr('Analysis year', 'Año del análisis')}</span>
                  <select
                    aria-label={tr('Analysis year', 'Año del análisis')}
                    value={selection.selected_year}
                    onChange={(e) => {
                      const year = Number(e.target.value)
                      change({
                        selected_year: year,
                        year_start: Math.min(year, selection.year_start),
                        year_end: Math.max(year, selection.year_end),
                      })
                    }}
                  >
                    {years.map((y) => (
                      <option key={y}>{y}</option>
                    ))}
                  </select>
                </label>
                <span>
                  {monthName}
                  <small>
                    {selected?.status === 'partial_archive'
                      ? tr('Partial archive', 'Archivo parcial')
                      : selected?.value == null
                        ? noData
                        : tr('Observed archive', 'Archivo observado')}
                  </small>
                </span>
              </div>
              <div className="month-axis">
                {SHORT.map((month, i) => (
                  <button
                    key={month}
                    aria-pressed={selection.selected_month === i + 1}
                    aria-label={`${MONTHS[i]} ${selection.selected_year}`}
                    onClick={() => change({ selected_month: i + 1 })}
                  >
                    <span>{month}</span>
                    <i
                      className={
                        analysis?.months.find(
                          (m) => m.year === selection.selected_year && m.month === i + 1,
                        )?.value == null
                          ? 'empty'
                          : ''
                      }
                    />
                  </button>
                ))}
              </div>
              <button
                className="time-export"
                aria-label={tr('Export analysis', 'Exportar análisis')}
                disabled={!analysis}
                onClick={() => setModal('export')}
              >
                <Download size={18} />
                <span>{tr('Export', 'Exportar')}</span>
              </button>
            </section>
            {tab === 'lab' && (
              <>
                <div className="comparison-note">
                  <Info size={17} />
                  <p>
                    {labHarmonized
                      ? tr(
                          'Left: the harmonized MODIS + VIIRS series, in VIIRS-equivalent active cell-days. Right: the original observations of the chosen sensor, in detections. The units differ: compare where and when there is activity, not the totals.',
                          'Izquierda: la serie armonizada MODIS + VIIRS, en celdas-día activas equivalentes VIIRS. Derecha: las observaciones originales del sensor elegido, en detecciones. Las unidades difieren: compara dónde y cuándo hay actividad, no los totales.',
                        )
                      : comparison?.note ||
                        tr(
                          'Original files from the same period. Their overpasses are not simultaneous, and the differences are not real changes in activity.',
                          'Archivos originales del mismo período. Sus pasadas no son simultáneas y las diferencias no equivalen a cambios reales de actividad.',
                        )}
                  </p>
                </div>
                <Experiment regions={regions} />
              </>
            )}
            {tab === 'atlas' && (
              <div className="atlas-caption">
                <span>
                  {isHarmonized
                    ? tr(
                        'NASA FIRMS data, harmonized · H3 cell centres, not individual fires.',
                        'Datos NASA FIRMS armonizados · centros de celdas H3, no incendios individuales.',
                      )
                    : tr(
                        'NASA FIRMS data · thermal pixels, not individual fires.',
                        'Datos NASA FIRMS · píxeles térmicos, no incendios individuales.',
                      )}
                </span>
                <button
                  onClick={() => {
                    setIntro(false)
                    setTab('lab')
                  }}
                >
                  {tr('Did the fire change, or the observer?', '¿Cambió el fuego o el observador?')}
                  <ArrowUpRight size={15} />
                </button>
              </div>
            )}
          </>
        )}
        {tab === 'calendar' && (
          <Calendar
            label={label}
            analysis={analysis}
            harmonized={harmonized}
            selection={selection}
            loading={loading}
            onChange={change}
            onOpenMap={() => {
              setIntro(false)
              setTab('atlas')
            }}
            onExport={() => setModal('export')}
            onAcquire={() => setTab('data')}
            report={
              <>
                <ReportButton className="button outline" body={reportBody()} onError={setError} />
                <button className="button outline" onClick={openAnalyst}>
                  <Sparkles size={16} />
                  {tr('Ask NINA', 'Pregúntale a NINA')}
                </button>
              </>
            }
          />
        )}
        {tab === 'priority' && (
          <Priority
            year={selection.selected_year}
            month={selection.selected_month}
            onChange={(year, month) =>
              change({
                selected_year: year,
                selected_month: month,
                year_start: Math.min(selection.year_start, year),
                year_end: Math.max(selection.year_end, year),
              })
            }
          />
        )}
        {tab === 'data' && (
          <DataPanel
            status={status}
            catalog={catalog}
            health={health}
            jobs={jobs}
            selection={selection}
            analysis={analysis}
            user={user}
            onRefresh={refresh}
            onNotice={setNotice}
            onError={setError}
          />
        )}
      </main>
      <footer className="site-footer">
        <span>
          NINA
          <span>
            {tr('Observation, context and evidence.', 'Observación, contexto y evidencia.')}
          </span>
        </span>
        <div>
          <button onClick={() => setTab('data')}>
            {tr('Sources and scope', 'Fuentes y alcance')}
          </button>
          <span>
            {tr(
              'Independent proposal · NASA Space Apps',
              'Propuesta independiente · NASA Space Apps',
            )}
          </span>
        </div>
      </footer>
      {tour && <Tour onClose={() => setTour(false)} />}
      <aside
        className={`analyst-drawer${analystOpen ? ' open' : ''}`}
        aria-hidden={!analystOpen}
        aria-label={tr('Ask NINA', 'Pregúntale a NINA')}
      >
        <header>
          <Sparkles size={16} />
          <strong>{tr('Ask NINA', 'Pregúntale a NINA')}</strong>
          <button onClick={() => setAnalystOpen(false)} aria-label={tr('Close the panel', 'Cerrar el panel')}>
            <X size={18} />
          </button>
        </header>
        <AnalystPanel context={reportBody()} onError={setError} onAction={runAnalystAction} />
      </aside>
      <Dialog
        harmonized={isHarmonized}
        modal={modal}
        onModal={setModal}
        label={label}
        analysis={analysis}
        selection={selection}
        health={health}
        user={user}
        onAccount={() => setAccountOpen(true)}
        onGeometry={applyGeometry}
        onDraw={() => {
          setModal('')
          setTab('atlas')
          setIntro(false)
          setDrawing(true)
        }}
        onShare={share}
        onError={setError}
        context={reportBody()}
        onAnalystAction={runAnalystAction}
      />
      <Account
        open={accountOpen}
        onOpen={setAccountOpen}
        user={user}
        onUser={setUser}
        onNotice={setNotice}
        onError={setError}
      />
    </div>
  )
}
