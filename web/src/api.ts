import { tr, locale, getLang } from './i18n'
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
export const sourceName = (source: string, platform?: string) =>
  SOURCES.find(([id]) => id === source + ':' + (source === 'modis' ? platform : 'all'))?.[1] ||
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
