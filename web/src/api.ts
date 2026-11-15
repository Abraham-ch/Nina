import { tr, locale, getLang } from './i18n'
import type {
  Analysis,
  AnalystAnswer,
  AnalystQuestion,
  AnalystStatus,
  HarmonizedAnalysis,
  HarmonizedPoints,
  HarmonizedReply,
  Points,
  PriorityTable,
  Reply,
  ReportCreated,
  ReportRequest,
  Selection,
} from './types'
export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + url, options)
  if (!response.ok) {
    let message = tr('The request could not be completed', 'No se pudo completar la consulta')
    try {
      const body = await response.json()
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new Error(message)
  }
  return response.json()
}
export const post = <T>(url: string, data: unknown, signal?: AbortSignal) =>
  api<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
  })
const MONTHS_EN = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]
const MONTHS_ES = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
]
export const months = () => (getLang() === 'es' ? MONTHS_ES : MONTHS_EN)
export const shortMonths = () => months().map((m) => m.slice(0, 3))
export const SOURCES = [
  ['modis:Aqua', 'MODIS · Aqua'],
  ['modis:Terra', 'MODIS · Terra'],
  ['modis:all', 'MODIS · Terra + Aqua'],
  ['viirs-snpp:all', 'VIIRS · S-NPP'],
  ['viirs-jpss1:all', 'VIIRS · NOAA-20'],
  ['viirs-jpss2:all', 'VIIRS · NOAA-21'],
]
export const fmt = (n: number | null | undefined, dec = 0) =>
  n == null
    ? '—'
    : new Intl.NumberFormat(locale(), {
        maximumFractionDigits: dec,
      }).format(n)
export const pct = (n: number | null | undefined) =>
  n == null ? tr('No comparison', 'Sin comparación') : `${n > 0 ? '+' : ''}${fmt(n, 1)}%`
export const bytes = (n: number) => (n >= 1e9 ? `${fmt(n / 1e9, 2)} GB` : `${fmt(n / 1e6, 2)} MB`)
// Harmonized product: one MODIS + VIIRS series, not a sensor. Experimental until it passes its gates.
export const HARMONIZED = 'harmonized'
export const harmonizedName = () => tr('Harmonized · MODIS + VIIRS', 'Armonizado · MODIS + VIIRS')
export const analysisPath = (harmonized: boolean) =>
  harmonized ? '/harmonized/analyses' : '/analyses'
// The harmonized API speaks in its own fields; these map it onto the calendar, map and dialog views.
export function fromHarmonized(
  h: HarmonizedAnalysis,
  selection: Selection,
  areaName: string,
): Analysis {
  const month = (m: HarmonizedAnalysis['selected']) => ({
    year: m.year,
    month: m.month,
    value: m.value,
    observed: m.observed_activity,
    historical_median: m.historical_median,
    historical_n: m.historical_n,
    anomaly_percent: m.anomaly_percent,
    // The calendar marks partial months with an asterisk; a null value stays a gap, never zero.
    status: m.partial_coverage || m.is_provisional ? 'partial_archive' : m.status,
    coverage_percent: null,
  })
  return {
    id: h.id,
    area_name: areaName,
    metric_label: tr(
      'Harmonized activity · VIIRS-equivalent active cell-days',
      'Actividad armonizada · celdas-día activas equivalentes VIIRS',
    ),
    selection,
    selected: month(h.selected),
    months: h.months.map(month),
    limitations: h.limitations,
    references: h.references,
    data_revision: h.dataset_id,
    software_revision: h.method_version,
    archive_windows: [],
    harmonization_status: h.validation_status,
    synthetic: false,
  }
}
export function pointsFromHarmonized(p: HarmonizedPoints, date: string): Points {
  return {
    type: 'FeatureCollection',
    total: p.total,
    shown: p.shown,
    sampling: p.sampled ? 'sampled' : 'all',
    synthetic: false,
    features: p.features.map((f) => ({
      type: 'Feature',
      geometry: f.geometry,
      properties: {
        id: f.properties.cell,
        source: HARMONIZED,
        platform: tr('H3 cell centre', 'Centro de celda H3'),
        date: f.properties.last_day || date,
        frp: f.properties.activity,
        confidence: f.properties.calibration_validated
          ? tr('Validated coefficient', 'Coeficiente validado')
          : tr('Unvalidated estimate', 'Estimación no validada'),
        daynight: '',
        scan: f.properties.observed_cell_days,
        track: null,
      },
    })),
  }
}
export const replyFromHarmonized = (r: HarmonizedReply): Reply => ({
  answer: r.answer,
  framing: null,
  guidance: '',
  engine: 'deterministic_grounded',
  evidence: [],
  references: r.references,
})
export const sourceName = (source: string, platform?: string) =>
  source === HARMONIZED
    ? harmonizedName()
    : SOURCES.find(([id]) => id === source + ':' + (source === 'modis' ? platform : 'all'))?.[1] ||
      source
const ES_NAMES: Record<string, string> = {
  Peru: 'Perú',
  Brazil: 'Brasil',
  Spain: 'España',
  France: 'Francia',
  Italy: 'Italia',
  Germany: 'Alemania',
  Mexico: 'México',
  'United States of America': 'Estados Unidos',
  'Dem. Rep. Congo': 'Rep. Dem. del Congo',
  'South Africa': 'Sudáfrica',
}
/** Country names come from Natural Earth in English; Spanish gets the common exonyms. */
export const translatedName = (name: string) => tr(name, ES_NAMES[name] || name)
// Territorial evidence report: the printable document is served by the API itself.
export const createReport = (body: ReportRequest) => post<ReportCreated>('/reports/territorial', body)
export const reportDocumentUrl = (id: string) => `/api/reports/territorial/${id}/document`
export const reportPackageUrl = (id: string) => `/api/reports/territorial/${id}/package`
export const askAnalyst = (body: AnalystQuestion) => post<AnalystAnswer>('/analyst', body)
export const analystStatus = () => api<AnalystStatus>('/analyst')
export const priorityTable = (year: number, month: number) =>
  post<PriorityTable>('/reports/priority', { year, month, language: getLang() })
