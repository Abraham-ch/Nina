import { shortMonths, sourceName, fmt } from './api'
import { tr } from './i18n'
import type { Analysis } from './types'
const xml = (s: string) =>
  s.replace(
    /[<>&"']/g,
    (c) =>
      ({
        '<': '&lt;',
        '>': '&gt;',
        '&': '&amp;',
        '"': '&quot;',
        "'": '&apos;',
      })[c]!,
  )
export function seasonSVG(analysis: Analysis) {
  const months = analysis.months.filter((m) => m.year === analysis.selection.selected_year),
    max = Math.max(1, ...months.flatMap((m) => [m.value || 0, m.historical_median || 0])) * 1.1
  const x = (i: number) => 65 + i * 69,
    y = (value: number) => 276 - (value / max) * 175
  function path(key: 'value' | 'historical_median') {
    let previous = false
    return months
      .map((m, i) => {
        const value = m[key]
        if (value == null) {
          previous = false
          return ''
        }
        const prefix = previous ? 'L' : 'M'
        previous = true
        return `${prefix}${x(i)},${y(value)}`
      })
      .join(' ')
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="400" viewBox="0 0 900 400"><title>${xml(analysis.area_name)} · ${tr('season', 'temporada')} ${analysis.selection.selected_year}</title><desc>${tr('Monthly detections and the median of the same month over up to ten previous years. Gaps are unavailable data. Observation coverage not reconstructed.', 'Detecciones mensuales y mediana del mismo mes de hasta diez años previos. Los huecos son datos no disponibles. Cobertura de observación no reconstruida.')}</desc><rect width="900" height="400" fill="#f5f5ef"/><g font-family="Arial,sans-serif" fill="#203a3c"><text x="35" y="38" font-size="24">NINA · ${xml(analysis.area_name)} · ${analysis.selection.selected_year}</text><text x="35" y="66" font-size="13">${xml(sourceName(analysis.selection.source, analysis.selection.platform))} · ${xml(analysis.metric_label)} · ${tr('UTC months', 'meses UTC')}</text><text x="65" y="92" font-size="11">${tr('Detections / month', 'Detecciones / mes')}</text>${[0, 0.5, 1].map((t) => `<line x1="65" x2="850" y1="${y(max * t)}" y2="${y(max * t)}" stroke="#d8ded5"/><text x="55" y="${y(max * t) + 4}" font-size="11" text-anchor="end">${fmt(max * t)}</text>`).join('')}<path d="${path('historical_median')}" stroke="#647973" stroke-width="2" stroke-dasharray="5 5" fill="none"/><path d="${path('value')}" stroke="#b8733d" stroke-width="2.5" fill="none"/>${shortMonths()
    .map((m, i) => `<text x="${x(i)}" y="302" font-size="11" text-anchor="middle">${m}</text>`)
    .join(
      '',
    )}<text x="35" y="337" font-size="12">${tr('Solid line: selected archive · Dashed line: historical median (minimum 5 years)', 'Serie continua: archivo seleccionado · Serie discontinua: mediana histórica (mínimo 5 años)')}</text><text x="35" y="360" font-size="11">${tr('NASA FIRMS · Detected pixels, not individual fires. Observation coverage not reconstructed.', 'NASA FIRMS · Píxeles detectados, no incendios individuales. Cobertura de observación no reconstruida.')}</text><text x="35" y="383" font-size="10">${tr('Analysis', 'Análisis')} ${analysis.id} · ${tr('Data revision', 'Revisión de datos')} ${analysis.data_revision}</text></g></svg>`
}
