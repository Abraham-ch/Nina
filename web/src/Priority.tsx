import { ArrowDown, ArrowUp, FileText } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { fmt, months, pct, priorityTable, reportDocumentUrl } from './api'
import { tr } from './i18n'
import type { PriorityRow, PriorityTable } from './types'

type Key = keyof PriorityRow
type Column = { key: Key; label: string; hint: string; render: (row: PriorityRow) => ReactNode }

const tone = (value: number | null, high = 10) =>
  value == null ? '' : value >= high ? 'up' : value <= -high ? 'down' : 'flat'

/**
 * Peruvian departments side by side for one month. Every indicator stays in its own sortable column:
 * NINA does not merge them into a single score, so the reader decides which one matters.
 */
export default function Priority({
  year,
  month,
  onChange,
}: {
  year: number
  month: number
  onChange: (year: number, month: number) => void
}) {
  const [table, setTable] = useState<PriorityTable | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(''),
    [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: 'month_anomaly', desc: true })
  const MONTHS = months()

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    priorityTable(year, month)
      .then((result) => alive && setTable(result))
      .catch((reason) => alive && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [year, month])

  const columns: Column[] = [
    {
      key: 'month_value',
      label: tr('Activity in the month', 'Actividad del mes'),
      hint: tr(
        'VIIRS-equivalent active cell-days: shows the size behind each percentage',
        'Celdas-día activas equivalentes VIIRS: muestra el tamaño detrás de cada porcentaje',
      ),
      render: (r) => (r.month_value == null ? <span className="muted">—</span> : fmt(r.month_value)),
    },
    {
      key: 'month_anomaly',
      label: tr('Month vs normal', 'Mes frente a lo normal'),
      hint: tr('Against the median of the other years', 'Respecto de la mediana de los demás años'),
      render: (r) =>
        r.month_anomaly == null ? (
          <span className="muted">{tr('n/a', 's/d')}</span>
        ) : (
          <span className={`chip ${tone(r.month_anomaly)}`}>{pct(r.month_anomaly)}</span>
        ),
    },
    {
      key: 'month_rank',
      label: tr('Rank of the month', 'Puesto del mes'),
      hint: tr('1 = highest of the compared years', '1 = el más alto de los años comparados'),
      render: (r) => (r.month_rank ? `${r.month_rank} / ${r.month_rank_of}` : '—'),
    },
    {
      key: 'season_rank',
      label: tr('Season Jul–Oct', 'Temporada jul–oct'),
      hint: tr('Rank of the fire season', 'Puesto de la temporada de incendios'),
      render: (r) => (r.season_rank ? `${r.season_rank} / ${r.season_rank_of}` : '—'),
    },
    {
      key: 'trend_harmonized',
      label: tr('Real trend', 'Tendencia real'),
      hint: tr('Harmonized, 2003 onwards, %/year', 'Armonizada, desde 2003, %/año'),
      render: (r) =>
        r.trend_harmonized_direction === 'increase' || r.trend_harmonized_direction === 'decrease' ? (
          <span className={`trend ${r.trend_harmonized_direction}`}>
            {r.trend_harmonized_direction === 'increase' ? <ArrowUp size={13} /> : <ArrowDown size={13} />}
            {fmt(r.trend_harmonized, 1)} %
          </span>
        ) : (
          <span className="muted">{tr('no trend', 'sin tendencia')}</span>
        ),
    },
    {
      key: 'significant_events',
      label: tr('Detected fires', 'Incendios detectados'),
      hint: tr('Events with at least 5 active cell-days, in the year', 'Eventos con al menos 5 celdas-día, en el año'),
      render: (r) => fmt(r.significant_events),
    },
    {
      key: 'emergencies',
      label: tr('INDECI emergencies', 'Emergencias INDECI'),
      hint: tr('Recorded forest-fire emergencies, in the year', 'Emergencias por incendio forestal registradas, en el año'),
      render: (r) => (r.emergencies == null ? <span className="muted">{tr('no record', 'sin registro')}</span> : fmt(r.emergencies)),
    },
    {
      key: 'forest_loss_ha',
      label: tr('Tree-cover loss (ha)', 'Pérdida arbórea (ha)'),
      hint: tr('Hansen/UMD, in the year', 'Hansen/UMD, en el año'),
      render: (r) => fmt(r.forest_loss_ha),
    },
    {
      key: 'drought',
      label: tr('Drought', 'Sequía'),
      hint: tr('In the month (NASA POWER)', 'En el mes (NASA POWER)'),
      render: (r) =>
        r.drought == null ? (
          <span className="muted">{tr('n/a', 'no aplica')}</span>
        ) : r.drought ? (
          <span className="chip up">{tr('Yes', 'Sí')}</span>
        ) : (
          tr('No', 'No')
        ),
    },
  ]

  const rows = useMemo(() => {
    const list = [...(table?.rows || [])]
    const value = (row: PriorityRow) => {
      const v = row[sort.key]
      return typeof v === 'boolean' ? Number(v) : v
    }
    list.sort((a, b) => {
      const x = value(a),
        y = value(b)
      if (x == null && y == null) return a.name.localeCompare(b.name)
      if (x == null) return 1
      if (y == null) return -1
      const ascending = sort.key === 'month_rank' || sort.key === 'season_rank'
      const order = (x as number) - (y as number)
      return (sort.desc !== ascending ? -order : order) || a.name.localeCompare(b.name)
    })
    return list
  }, [table, sort])

  const years = Array.from({ length: new Date().getFullYear() - 2001 }, (_, i) => 2002 + i).reverse()

  return (
    <section className="calendar-page priority-page" aria-busy={loading}>
      <div className="section-title">
        <div>
          <span className="kicker">{tr('Where to look first', 'Dónde mirar primero')}</span>
          <h1>{tr('Territorial priorities.', 'Prioridades territoriales.')}</h1>
          <p>
            {tr(
              'Peruvian departments compared for the selected month. Each indicator is separate and sortable: NINA does not combine them into a score.',
              'Departamentos del Perú comparados en el mes seleccionado. Cada indicador va por separado y se puede ordenar: NINA no los combina en un puntaje.',
            )}
          </p>
        </div>
      </div>
      <div className="calendar-controls">
        <label>
          {tr('Month', 'Mes')}
          <select value={month} onChange={(e) => onChange(year, Number(e.target.value))}>
            {MONTHS.map((name, index) => (
              <option key={name} value={index + 1}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {tr('Year', 'Año')}
          <select value={year} onChange={(e) => onChange(Number(e.target.value), month)}>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <span className="calendar-state">
          {loading
            ? tr('Computing the 25 departments (first time ~20 s)…', 'Calculando los 25 departamentos (la primera vez ~20 s)…')
            : table
              ? `${MONTHS[table.month - 1]} ${table.year}`
              : ''}
        </span>
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="table-scroll priority-table">
        <table>
          <thead>
            <tr>
              <th>{tr('Department', 'Departamento')}</th>
              {columns.map((column) => (
                <th key={column.key} title={column.hint}>
                  <button
                    className="sort"
                    aria-sort={sort.key === column.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}
                    onClick={() =>
                      setSort((current) => ({
                        key: column.key,
                        desc: current.key === column.key ? !current.desc : true,
                      }))
                    }
                  >
                    {column.label}
                    {sort.key === column.key && (sort.desc ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                  </button>
                </th>
              ))}
              <th>{tr('Report', 'Informe')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.code}>
                <th scope="row">{row.name}</th>
                {columns.map((column) => (
                  <td key={column.key}>{column.render(row)}</td>
                ))}
                <td>
                  <a className="text-link" href={reportDocumentUrl(row.report_id)} target="_blank" rel="noreferrer">
                    <FileText size={13} /> {tr('Open', 'Abrir')}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table && <p className="priority-note">{tr(
        'Detected fires: harmonized satellite events (VIIRS era). Emergencies: INDECI records with damage assessment, not every fire. "n/a" means no comparable value, never zero.',
        'Incendios detectados: eventos satelitales armonizados (era VIIRS). Emergencias: registros de INDECI con evaluación de daños, no todo incendio. "s/d" significa sin valor comparable, nunca cero.',
      )}</p>}
    </section>
  )
}
