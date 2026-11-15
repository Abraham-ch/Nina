import { tr } from './i18n'
import type { AnalystVisual } from './types'

const WIDTH = 640
const HEIGHT = 230
const PAD = { left: 52, right: 12, top: 14, bottom: 34 }
const COLORS = ['var(--viirs)', 'var(--modis)']

/** Numbers as the assistant writes them: comma for thousands, point for decimals, in both languages. */
export function formatValue(value: number | string | null): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2
  return value.toLocaleString('en-US', { maximumFractionDigits: digits })
}

function ticks(min: number, max: number): number[] {
  if (max === min) return [min]
  return [min, min + (max - min) / 2, max]
}

/** Line or bar chart: a gap is a break in the line or a missing bar, never zero. */
function Chart({ visual }: { visual: AnalystVisual }) {
  const values = visual.series.flatMap((s) => s.values).filter((v): v is number => v !== null)
  if (values.length === 0)
    return <p className="small-note">{tr('No comparable values to draw.', 'No hay valores comparables para dibujar.')}</p>
  const reference = visual.reference_value
  const top = Math.max(...values, reference ?? 0)
  const bottom = Math.min(0, ...values)
  const n = visual.categories.length
  const innerW = WIDTH - PAD.left - PAD.right
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const y = (v: number) => PAD.top + innerH - ((v - bottom) / (top - bottom || 1)) * innerH
  const step = innerW / Math.max(n, 1)
  const x = (i: number) => PAD.left + step * i + step / 2
  const labelEvery = Math.max(1, Math.ceil(n / 8))
  const bars = visual.chart === 'bar'
  const barWidth = Math.max(1.5, (step * 0.8) / visual.series.length)
  return (
    <svg
      className="analyst-chart"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={`${visual.title}. ${visual.unit ?? ''}`}
    >
      {ticks(bottom, top).map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
          <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="axis">
            {formatValue(t)}
          </text>
        </g>
      ))}
      {visual.categories.map((c, i) =>
        i % labelEvery === 0 || c === visual.highlight ? (
          <text key={c} x={x(i)} y={HEIGHT - PAD.bottom + 16} textAnchor="middle" className="axis">
            {c}
          </text>
        ) : null,
      )}
      {visual.highlight && visual.categories.includes(visual.highlight) && (
        <rect
          className="highlight"
          x={x(visual.categories.indexOf(visual.highlight)) - step / 2}
          y={PAD.top}
          width={step}
          height={innerH}
        />
      )}
      {visual.series.map((s, k) =>
        bars ? (
          <g key={s.name} fill={COLORS[k % COLORS.length]}>
            {s.values.map((v, i) =>
              v === null ? null : (
                <rect
                  key={i}
                  x={x(i) - (barWidth * visual.series.length) / 2 + barWidth * k}
                  y={Math.min(y(v), y(0))}
                  width={barWidth}
                  height={Math.abs(y(0) - y(v))}
                >
                  <title>{`${visual.categories[i]} · ${s.name}: ${formatValue(v)}`}</title>
                </rect>
              ),
            )}
          </g>
        ) : (
          <g key={s.name}>
            <path
              className="series"
              stroke={COLORS[k % COLORS.length]}
              d={s.values
                .map((v, i) => (v === null ? '' : `${i === 0 || s.values[i - 1] === null ? 'M' : 'L'}${x(i)},${y(v)}`))
                .join(' ')}
            />
            {s.values.map((v, i) =>
              v === null ? null : (
                <circle key={i} cx={x(i)} cy={y(v)} r={n > 40 ? 1.6 : 2.6} fill={COLORS[k % COLORS.length]}>
                  <title>{`${visual.categories[i]} · ${s.name}: ${formatValue(v)}`}</title>
                </circle>
              ),
            )}
          </g>
        ),
      )}
      {reference !== null && (
        <g>
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(reference)} y2={y(reference)} className="reference" />
          <text x={WIDTH - PAD.right} y={y(reference) - 4} textAnchor="end" className="axis">
            {visual.reference_label}: {formatValue(reference)}
          </text>
        </g>
      )}
    </svg>
  )
}

/** A chart or table produced by NINA for an answer, with its unit, note and source. */
export default function AnalystVisualView({ visual }: { visual: AnalystVisual }) {
  return (
    <figure className="analyst-visual">
      <figcaption>
        <strong>{visual.title}</strong>
        {visual.unit && <span>{visual.unit}</span>}
      </figcaption>
      {visual.type === 'chart' ? (
        <>
          <Chart visual={visual} />
          {visual.series.length > 1 && (
            <ul className="analyst-legend">
              {visual.series.map((s, k) => (
                <li key={s.name}>
                  <i style={{ background: COLORS[k % COLORS.length] }} />
                  {s.name}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="analyst-table">
          <table>
            <thead>
              <tr>
                {visual.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visual.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className={typeof cell === 'number' ? 'num' : undefined}>
                      {formatValue(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {visual.note && <p className="small-note">{visual.note}</p>}
      <p className="analyst-source">
        {tr('Source', 'Fuente')}: {visual.source}
      </p>
    </figure>
  )
}
