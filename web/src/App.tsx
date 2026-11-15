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
  Play,
  Share2,
  X,
  Check,
  SlidersHorizontal,
  Compass,
  CircleHelp,
  UserRound,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useState, type PointerEvent as ReactPointerEvent } from 'react'

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
} from './api'
import Calendar from './Calendar'
import DataPanel from './DataPanel'
import Dialog from './Dialog'
import Experiment from './Experiment'
import { tr, locale } from './i18n'
import LangSwitch from './LangSwitch'
import Tour from './Tour'
import type {
  Analysis,
  Catalog,
  Comparison,
  Geometry,
  Health,
  Job,
  Layer,
  Places,
  Point,
  Points,
  Regions,
  Selection,
  Status,
  User,
} from './types'
const Globe = lazy(() => import('./Globe'))
export type Tab = 'atlas' | 'calendar' | 'lab' | 'data'
export type Modal = '' | 'evidence' | 'export' | 'explain' | 'area'
const NOW = new Date()
const DEFAULT: Selection = {
  scope: 'world',
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
        place: String(value.place || 'world'),
        tab: (['atlas', 'calendar', 'lab', 'data'].includes(value.tab)
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
    place: 'world',
    tab: 'atlas' as Tab,
    linked: false,
  }
}
const linked = readLink()
const stories = () => [
  {
    tag: tr('The archive', 'El archivo'),
    title: tr('Did the fire change, or the observer?', '¿Cambió el fuego o el observador?'),
    copy: tr(
      'We start in Peru, September 2025, and examine the same territory with different generations of sensors.',
      'Empezamos en Perú, septiembre de 2025. Examinamos el mismo territorio con distintas generaciones de sensores.',
    ),
    action: tr('Compare observers', 'Comparar observadores'),
  },
  {
    tag: tr('The observers', 'Los observadores'),
    title: tr('The instrument leaves a signal too.', 'El instrumento también deja una señal.'),
    copy: tr(
      'Slide the comparison between MODIS Aqua and VIIRS S-NPP. Same area, same month; their overpasses and resolution differ.',
      'Desliza la comparación entre MODIS Aqua y VIIRS S-NPP. Es la misma área y el mismo mes; sus pasadas y resolución son diferentes.',
    ),
    action: tr('Test the continuity', 'Poner a prueba la continuidad'),
  },
  {
    tag: tr('The evidence', 'La evidencia'),
    title: tr('An estimate deserves a test.', 'Una estimación merece una prueba.'),
    copy: tr(
      'Reveal the Aqua reference and review the error on a held-out period. It is an exploratory test: observation opportunities are not controlled yet.',
      'Revela la referencia Aqua y revisa el error en un período reservado. Es una prueba exploratoria: falta controlar las oportunidades de observación.',
    ),
    action: tr('Finish the tour', 'Terminar recorrido'),
  },
]

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
    [story, setStory] = useState<number | null>(null),
    [viirs, setViirs] = useState('viirs-snpp'),
    [extraFilters, setExtraFilters] = useState(false),
    [tour, setTour] = useState(false)
  const [user, setUser] = useState<User | null>(null),
    [accountOpen, setAccountOpen] = useState(false)
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
    refresh()
  }, [])
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
  useEffect(() => {
    if (selection.scope === 'custom' && !selection.geometry) return
    const abort = new AbortController()
    setLoading(true)
    setAnalysis(null)
    setPoints(null)
    setComparison(null)
    setInspected(null)
    post<Analysis>('/analyses', selection, abort.signal)
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
  }, [JSON.stringify(selection), dataRevision])
  useEffect(() => {
    if (!analysis) return
    const abort = new AbortController()
    api<Points>(`/analyses/${analysis.id}/points`, { signal: abort.signal })
      .then(setPoints)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => abort.abort()
  }, [analysis?.id])
  useEffect(() => {
    if (!analysis || tab !== 'lab') return
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
    SHORT = shortMonths(),
    STORIES = stories()
  const country = places?.features.find((p) => `country:${p.properties.id}` === placeId) || null
  const department =
    regions?.geojson.features.find((p) => p.properties.id === selection.department) || null
  const currentPlace =
    department ||
    country ||
    (selection.scope === 'PER'
      ? places?.features.find((p) => p.properties.name === 'Peru') || null
      : null)
  const label =
    analysis?.area_name ||
    (placeId === 'world'
      ? tr('The planet', 'El planeta')
      : placeId === 'PER'
        ? tr('All of Peru', 'Perú completo')
        : country
          ? translatedName(country.properties.name)
          : selection.area_label || tr('Your selection', 'Tu selección'))
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
    setStory(null)
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
        year_start: 2018,
        source: 'modis',
        platform: 'Aqua',
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
  function selectSource(value: string) {
    const [source, platform] = value.split(':')
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
  function startStory() {
    setPlaceId('PER')
    setSelection({
      ...DEFAULT,
      scope: 'PER',
      source: 'modis',
      platform: 'Aqua',
      year_start: 2018,
      year_end: 2025,
      selected_year: 2025,
      selected_month: 9,
    })
    setIntro(false)
    setStory(0)
    setTab('atlas')
    setFlat(false)
    setViirs('viirs-snpp')
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  function startTour() {
    setIntro(false)
    setStory(null)
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
  function nextStory() {
    if (story === null) return
    if (story === 0) {
      setStory(1)
      setTab('lab')
      setFlat(true)
      window.scrollTo({ top: 0, behavior: 'instant' })
    } else if (story === 1) {
      setStory(2)
      setTimeout(
        () =>
          document.getElementById('substitution')?.scrollIntoView({
            behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
              ? 'instant'
              : 'smooth',
            block: 'center',
          }),
        60,
      )
    } else setStory(null)
  }
  const selected = analysis?.selected
  const layers: Layer[] =
    tab === 'lab'
      ? comparison?.layers || []
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
  const displayed = layers.reduce((sum, l) => sum + l.points.shown, 0),
    total = layers.reduce((sum, l) => sum + l.points.total, 0)
  const firstYear = selection.scope === 'PER' ? 2000 : 2025
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
          <LangSwitch />
          <button
            className="tour-start"
            onClick={startTour}
            aria-label={tr('Platform guide', 'Guía de la plataforma')}
          >
            <CircleHelp size={16} />
            <span>{tr('Guide', 'Guía')}</span>
          </button>
          <button className="story-start" onClick={startStory}>
            <Play size={13} fill="currentColor" />
            {tr('Expedition', 'Expedición')}
          </button>
          <button className={tab === 'data' ? 'active' : ''} onClick={() => setTab('data')}>
            <BookOpen size={17} />
            <span>{tr('Sources', 'Fuentes')}</span>
          </button>
          <button
            onClick={() => setAccountOpen(true)}
            aria-label={
              user ? `Account for ${user.email}` : tr('Sign in to NINA', 'Entrar en NINA')
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
            {SOURCES.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button className="coordinates-button" onClick={() => setModal('area')}>
          <Compass size={16} />
          <span>{tr('Coordinates', 'Coordenadas')}</span>
        </button>
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
                  busy={loading || (tab === 'lab' ? !comparison : !points)}
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
                    </span>
                    <h1>{label}</h1>
                    <div className="observed-number">
                      {loading ? '…' : fmt(selected?.value)}
                      <span>
                        {tr('archive detections', 'detecciones del archivo')}
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
                      <button onClick={() => setModal('explain')} disabled={!analysis}>
                        <MessageSquareText size={15} />
                        {tr('Explain', 'Explicar')}
                      </button>
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
                      {tr(
                        'The observer changes the signal too.',
                        'El observador también cambia la señal.',
                      )}
                    </h1>
                    <p>
                      {label} · {monthName} {selection.selected_year}
                    </p>
                  </div>
                  <div className="sensor-tag left">
                    <i className="modis-square" />
                    <span>
                      MODIS Aqua
                      <strong>
                        {comparison?.layers[0]?.selected.value == null
                          ? noData
                          : fmt(comparison.layers[0].selected.value) +
                            ' ' +
                            tr('detections', 'detecciones')}
                      </strong>
                    </span>
                  </div>
                  <div className="sensor-tag right">
                    <i className="viirs-circle" />
                    <span>
                      {sourceName(viirs, 'all')}
                      <strong>
                        {comparison?.layers[1]?.selected.value == null
                          ? noData
                          : fmt(comparison.layers[1].selected.value) +
                            ' ' +
                            tr('detections', 'detecciones')}
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
                    <select
                      aria-label={tr('VIIRS to compare', 'VIIRS de comparación')}
                      value={viirs}
                      onChange={(e) => setViirs(e.target.value)}
                    >
                      <option value="viirs-snpp">VIIRS · S-NPP</option>
                      <option value="viirs-jpss1">VIIRS · NOAA-20</option>
                      <option value="viirs-jpss2">VIIRS · NOAA-21</option>
                    </select>
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
                    {tr('One archive observation', 'Una observación del archivo')}
                  </span>
                  <h2>{inspected.properties.platform}</h2>
                  <dl>
                    <dt>{tr('UTC date', 'Fecha UTC')}</dt>
                    <dd>{inspected.properties.date}</dd>
                    <dt>{tr('Coordinates', 'Coordenadas')}</dt>
                    <dd>{inspected.geometry.coordinates.map((n) => n.toFixed(4)).join(', ')}</dd>
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
                </aside>
              )}
              <div className="map-data-note">
                <span>
                  {tab === 'lab' ? (
                    <>
                      <i className="modis-square" />
                      MODIS
                      <i className="viirs-circle" />
                      VIIRS
                    </>
                  ) : (
                    <>
                      <i
                        className={selection.source === 'modis' ? 'modis-square' : 'viirs-circle'}
                      />
                      {sourceName(selection.source, selection.platform)}
                    </>
                  )}
                </span>
                <span>
                  {loading || !points || (tab === 'lab' && !comparison)
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
                    {comparison?.note ||
                      tr(
                        'Original files from the same period. Their overpasses are not simultaneous, and the differences are not real changes in activity.',
                        'Archivos originales del mismo período. Sus pasadas no son simultáneas y las diferencias no equivalen a cambios reales de actividad.',
                      )}
                  </p>
                </div>
                <Experiment regions={regions} revealForStory={story === 2} />
              </>
            )}
            {tab === 'atlas' && (
              <div className="atlas-caption">
                <span>
                  {tr(
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
            analysis={analysis}
            selection={selection}
            loading={loading}
            onChange={change}
            onOpenMap={() => {
              setIntro(false)
              setTab('atlas')
            }}
            onExport={() => setModal('export')}
            onAcquire={() => setTab('data')}
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
      {story !== null && (
        <aside className="story-panel" aria-label={tr('Guided expedition', 'Expedición guiada')}>
          <div>
            <span>
              {story + 1} / 3 · {STORIES[story].tag}
            </span>
            <button
              onClick={() => setStory(null)}
              aria-label={tr('Close expedition', 'Cerrar expedición')}
            >
              <X size={17} />
            </button>
          </div>
          <h2>{STORIES[story].title}</h2>
          <p>{STORIES[story].copy}</p>
          <button className="button sand" onClick={nextStory}>
            {STORIES[story].action}
            <ArrowRight size={16} />
          </button>
        </aside>
      )}
      {tour && <Tour onClose={() => setTour(false)} />}
      <Dialog
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
