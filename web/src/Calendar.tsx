import { ArrowUpRight, Download } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { fmt, months, shortMonths, pct, HARMONIZED } from './api'
import { tr, locale } from './i18n'
import type { Analysis, HarmonizedAnalysis, Month, Selection } from './types'

const shades = [
  '#f5eee2',
  '#efe0c4',
  '#e6c99a',
  '#deb273',
  '#cc8e50',
  '#b66b38',
  '#984a2b',
  '#733323',
]
function cellStyle(month: Month | undefined, maximum: number) {
  if (month?.value == null) return {}
  const index = Math.min(7, Math.floor((Math.log1p(month.value) / Math.log1p(maximum)) * 7))
  return {
    background: shades[index],
    color: index > 4 ? '#fff9ec' : '#3c372f',
  }
}
export function Trend({ analysis }: { analysis: Analysis | null }) {
  const harmonized = analysis?.selection.source === HARMONIZED
  const unit = harmonized
    ? tr('equivalent active cell-days', 'celdas-día activas equivalentes')
    : tr('detections', 'detecciones')
  const ref = useRef<HTMLDivElement>(null),
    [width, setWidth] = useState(640)
  useEffect(() => {
    const observer = new ResizeObserver((e) => setWidth(Math.max(280, e[0].contentRect.width)))
    if (ref.current) observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  const values = analysis?.months.filter((m) => m.year === analysis.selection.selected_year) || []
  const max = Math.max(1, ...values.flatMap((m) => [m.value || 0, m.historical_median || 0])) * 1.1
  const x = (i: number) => 48 + (i * (width - 66)) / 11,
    y = (v: number) => 174 - (v / max) * 140
  const MONTHS = months(),
    SHORT = shortMonths()
  function line(key: 'value' | 'historical_median') {
    let active = false
    return values
      .map((m, i) => {
        const value = m[key]
        if (value == null) {
          active = false
          return ''
        }
        const prefix = active ? 'L' : 'M'
        active = true
        return `${prefix}${x(i)},${y(value)}`
      })
      .join(' ')
  }
  return (
    <div ref={ref} className="trend">
      <svg
        id="season-chart"
        width="100%"
        height="220"
        viewBox={`0 0 ${width} 220`}
        role="img"
        aria-label={tr(
          `Monthly detections for ${analysis?.area_name || 'the selection'} and the historical median of the same month. Gaps are unavailable data.`,
          `Detecciones mensuales de ${analysis?.area_name || 'la selección'} y mediana histórica del mismo mes. Los huecos representan datos no disponibles.`,
        )}
      >
        <title>
          {tr('Seasonal profile', 'Perfil estacional')} · {analysis?.selection.selected_year}
        </title>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={48} x2={width - 15} y1={y(max * t)} y2={y(max * t)} stroke="#d9ded8" />
            <text x={40} y={y(max * t) + 4} textAnchor="end" fontSize={11} fill="#65716d">
              {new Intl.NumberFormat(locale(), {
                notation: 'compact',
                maximumFractionDigits: 1,
              }).format(max * t)}
            </text>
          </g>
        ))}
        <text x={48} y={15} fill="#65716d" fontSize={11}>
          {harmonized
            ? tr('Equivalent active cell-days / month', 'Celdas-día activas equivalentes / mes')
            : tr('Detections / month', 'Detecciones / mes')}
        </text>
        <path
          d={line('historical_median')}
          stroke="#647973"
          strokeWidth={2}
          strokeDasharray="5 5"
          fill="none"
        />
        <path d={line('value')} stroke="#b8733d" strokeWidth={2.5} fill="none" />
        {values.map((m, i) => (
          <g key={m.month}>
            {m.value != null && (
              <circle
                cx={x(i)}
                cy={y(m.value)}
                r={m.month === analysis?.selection.selected_month ? 5 : 2.5}
                fill="#b8733d"
              >
                <title>
                  {MONTHS[i]}: {fmt(m.value)} {unit}
                </title>
              </circle>
            )}
            <text x={x(i)} y={202} fontSize={11} fill="#65716d" textAnchor="middle">
              {SHORT[i]}
            </text>
          </g>
        ))}
      </svg>
      <div className="chart-key">
        <span>
          <i />
          {tr('Selected series', 'Serie seleccionada')}
        </span>
        <span>
          <i className="dashed" />
          {harmonized
            ? tr(
                'Median of the same month in the other eligible years',
                'Mediana del mismo mes en los demás años elegibles',
              )
            : tr(
                'Median of the same month, up to 10 previous years',
                'Mediana del mismo mes, hasta 10 años previos',
              )}
        </span>
      </div>
    </div>
  )
}

export default function Calendar({
  label,
  analysis,
  harmonized,
  selection,
  loading,
  onChange,
  onOpenMap,
  onExport,
  onAcquire,
  report,
}: {
  label: string
  analysis: Analysis | null
  harmonized: HarmonizedAnalysis | null
  selection: Selection
  loading: boolean
  onChange: (s: Partial<Selection>) => void
  onOpenMap: () => void
  onExport: () => void
  onAcquire: () => void
  report?: ReactNode
}) {
  const isHarmonized = selection.source === HARMONIZED
  const firstYear =
    isHarmonized && selection.scope !== 'world' ? 2002 : selection.scope === 'PER' ? 2000 : 2025
  const unit = isHarmonized
    ? tr('equivalent active cell-days', 'celdas-día activas equivalentes')
    : tr('detections', 'detecciones')
  const MONTHS = months(),
    SHORT = shortMonths()
  const years = Array.from(
    { length: selection.year_end - selection.year_start + 1 },
    (_, i) => selection.year_end - i,
  )
  const maximum = Math.max(1, ...(analysis?.months.map((m) => m.value || 0) || []))
  const lookup = new Map(analysis?.months.map((m) => [`${m.year}-${m.month}`, m]))
  const button = (y: number, m: number) => {
    const month = lookup.get(`${y}-${m}`)
    return (
      <button
        type="button"
        data-calendar-month={`${y}-${m}`}
        style={cellStyle(month, maximum)}
        className={
          month?.value == null ? 'no-data' : month.status === 'partial_archive' ? 'partial' : ''
        }
        aria-pressed={selection.selected_year === y && selection.selected_month === m}
        aria-label={`${MONTHS[m - 1]} ${y}: ${month?.value == null ? tr('no data available', 'sin datos disponibles') : fmt(month.value) + ' ' + unit + (month.status === 'partial_archive' ? tr(', partial archive', ', archivo parcial') : '')}`}
        onClick={() => onChange({ selected_year: y, selected_month: m })}
      >
        <span className="mobile-month">{SHORT[m - 1]}</span>
        {fmt(month?.value)}
        {month?.status === 'partial_archive' && <sup>*</sup>}
      </button>
    )
  }
  return (
    <section className="calendar-page" aria-busy={loading}>
      <div className="section-title">
        <div>
          <span className="kicker">
            {tr('Time reveals the pattern', 'El tiempo revela el patrón')}
          </span>
          <h1>{tr('The fire calendar.', 'El calendario del fuego.')}</h1>
          <p>
            {tr('The story of ', 'La historia de ')}
            <strong>{label}</strong>
            {tr(', month by month.', ', mes a mes.')}
          </p>
        </div>
        <div className="section-actions">
          {report}
          <button className="button outline" onClick={onExport} disabled={!analysis}>
            <Download size={16} />
            {tr('Export', 'Exportar')}
          </button>
        </div>
      </div>
      <div className="calendar-context">
        <div>
          <span>{tr('Selected period', 'Período seleccionado')}</span>
          <strong>
            {MONTHS[selection.selected_month - 1]} {selection.selected_year}
          </strong>
        </div>
        <div>
          <span>
            {isHarmonized
              ? tr('Harmonized activity', 'Actividad armonizada')
              : tr('Archive detections', 'Detecciones del archivo')}
          </span>
          <strong>{fmt(analysis?.selected.value)}</strong>
        </div>
        <div>
          <span>{tr('Against its median', 'Frente a su mediana')}</span>
          <strong>{pct(analysis?.selected.anomaly_percent)}</strong>
        </div>
        <button className="text-link" onClick={onOpenMap}>
          {tr('See this month on the map', 'Ver este mes en el mapa')}
          <ArrowUpRight size={15} />
        </button>
      </div>
      <div className="calendar-controls">
        <label>
          {tr('From', 'Desde')}
          <input
            aria-label={tr('First calendar year', 'Primer año del calendario')}
            type="number"
            min={firstYear}
            max={selection.year_end}
            value={selection.year_start}
            onChange={(e) => {
              const y = Number(e.target.value)
              if (y >= firstYear && y <= selection.year_end)
                onChange({
                  year_start: y,
                  selected_year: Math.max(y, selection.selected_year),
                })
            }}
          />
        </label>
        <label>
          {tr('To', 'Hasta')}
          <input
            aria-label={tr('Last calendar year', 'Último año del calendario')}
            type="number"
            min={selection.year_start}
            max={new Date().getUTCFullYear()}
            value={selection.year_end}
            onChange={(e) => {
              const y = Number(e.target.value)
              if (y >= selection.year_start && y <= 2100)
                onChange({
                  year_end: y,
                  selected_year: Math.min(y, selection.selected_year),
                })
            }}
          />
        </label>
        <button
          className="text-link"
          onClick={() =>
            onChange(
              isHarmonized && selection.scope !== 'world'
                ? { year_start: 2002 }
                : selection.scope === 'PER'
                  ? { year_start: 2000 }
                  : {
                      year_start: 2025,
                      year_end: 2026,
                      selected_year: Math.max(2025, Math.min(2026, selection.selected_year)),
                    },
            )
          }
        >
          {isHarmonized && selection.scope !== 'world'
            ? tr('Open from 2002', 'Abrir desde 2002')
            : selection.scope === 'PER'
              ? tr('Open from 2000', 'Abrir desde 2000')
              : tr('Global period 2025–2026', 'Período mundial 2025–2026')}
        </button>
        <span className="calendar-state">
          {loading
            ? tr('Querying the archive…', 'Consultando archivo…')
            : analysis?.selected.status === 'partial_archive'
              ? tr('Partial month · comparison omitted', 'Mes parcial · comparación omitida')
              : analysis?.selected.value == null
                ? tr('No archive for this month', 'Sin archivo para este mes')
                : isHarmonized
                  ? tr(
                      'Harmonized MODIS + VIIRS series · experimental',
                      'Serie armonizada MODIS + VIIRS · experimental',
                    )
                  : tr(
                      'Observed archive · coverage not corrected',
                      'Archivo observado · cobertura no corregida',
                    )}
        </span>
      </div>
      <div className="calendar-table">
        <table>
          <caption className="sr-only">
            {tr(
              'Monthly counts by year. An asterisk marks a partial period.',
              'Conteos mensuales por año. Un asterisco señala un período parcial.',
            )}
          </caption>
          <thead>
            <tr>
              <th>{tr('Year', 'Año')}</th>
              {SHORT.map((m) => (
                <th key={m}>{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y}>
                <th scope="row">{y}</th>
                {MONTHS.map((_, i) => (
                  <td key={i}>{button(y, i + 1)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="calendar-mobile">
        {years.map((y) => (
          <details key={y} open={y === selection.selected_year}>
            <summary>
              {y}
              <span>
                {fmt(
                  analysis?.months.filter((m) => m.year === y).filter((m) => m.value != null)
                    .length,
                )}{' '}
                {tr('months with records', 'meses con registros')}
              </span>
            </summary>
            <div className="month-grid">
              {MONTHS.map((_, i) => (
                <div key={i}>{button(y, i + 1)}</div>
              ))}
            </div>
          </details>
        ))}
      </div>
      <div className="calendar-legend">
        <span>
          <i className="hatch" />
          {tr('No data available', 'Sin datos disponibles')}
        </span>
        <span>
          {tr(
            '* Partial period or unknown completeness',
            '* Período parcial o integridad desconocida',
          )}
        </span>
        <span>
          0<i className="heat-scale" />
          {fmt(maximum)} {unit} · {tr('logarithmic scale', 'escala logarítmica')}
        </span>
      </div>
      {harmonized && (
        <div className="harmonized-note" role="note">
          <p>
            {tr(
              `Method ${harmonized.method_version}, dataset ${harmonized.dataset_id}. The unit is VIIRS-equivalent active cell-days: comparable activity across sensors, not a number of fires or burned area. A hatched month has no valid support; it is not zero.`,
              `Método ${harmonized.method_version}, conjunto ${harmonized.dataset_id}. La unidad son celdas-día activas equivalentes VIIRS: actividad comparable entre sensores, no número de incendios ni área quemada. Un mes rayado no tiene soporte válido; no es cero.`,
            )}
          </p>
          <p className="harmonized-legal">{harmonized.legal}</p>
        </div>
      )}
      {!isHarmonized &&
        (analysis?.selected.value == null || analysis?.selected.status === 'partial_archive') && (
          <div className="archive-prompt">
            <div>
              <strong>
                {analysis?.selected.value == null
                  ? tr(
                      'This month is not in your archive yet.',
                      'Este mes todavía no está en tu archivo.',
                    )
                  : tr(
                      'The completeness of this month is not verified.',
                      'La integridad de este mes no está verificada.',
                    )}
              </strong>
              <p>
                {tr(
                  'You can add this month from FIRMS for this area. Availability is checked before downloading.',
                  'Puedes incorporar el mes de FIRMS para esta área. La disponibilidad se verifica antes de descargar.',
                )}
              </p>
            </div>
            <button className="button dark" onClick={onAcquire}>
              {tr('Add data', 'Incorporar datos')}
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}
      <section className="season-section">
        <div>
          <span className="kicker">
            {tr('Compare it with its own history', 'Comparar con su propia historia')}
          </span>
          <h2>{tr('The shape of a season.', 'La forma de una temporada.')}</h2>
          <p>
            {selection.selected_year} · {analysis?.metric_label}.{' '}
            {tr(
              'The median needs at least five eligible years.',
              'La mediana requiere al menos cinco años elegibles.',
            )}
          </p>
        </div>
        <Trend analysis={analysis} />
      </section>
    </section>
  )
}
