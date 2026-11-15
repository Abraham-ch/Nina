import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { tr } from './i18n'

// Platform guide for newcomers: highlights each control and explains the concept behind it.
type Step = { target?: string; title: string; body: string }
const steps = (): Step[] => [
  {
    title: tr('Welcome to NINA', 'Bienvenida a NINA'),
    body: tr(
      'NINA brings together the heat detections that NASA satellites have recorded since 2000. Each detection is a thermal pixel: an area of 375 m to 1 km that is hotter than its surroundings. It is not an individual fire; many detections can belong to the same fire.',
      'NINA reúne las detecciones de calor que los satélites de la NASA registran desde 2000. Cada detección es un píxel térmico: un área de 375 m a 1 km más caliente que su entorno. No equivale a un incendio individual; muchas detecciones pueden pertenecer al mismo fuego.',
    ),
  },
  {
    target: '.territory-field',
    title: tr('1 · Where?', '1 · ¿Dónde?'),
    body: tr(
      'Pick the territory: the planet, Peru with its historical archive, any country or a Peruvian region. Everything you see (map, calendar and exports) is recomputed for that area.',
      'Elige el territorio: el planeta, el Perú con su archivo histórico, cualquier país o una región peruana. Todo lo que ves (mapa, calendario y exportaciones) se recalcula para esa área.',
    ),
  },
  {
    target: '.sensor-field',
    title: tr('2 · Through which eyes?', '2 · ¿Con qué ojos?'),
    body: tr(
      'Each satellite is a different observer. MODIS (1 km) has watched since 2000; VIIRS (375 m) since 2012 and sees more detail, so it detects more hotspots on the same fire. That is why NINA never adds their counts together: it always compares within the same observer.',
      'Cada satélite es un observador distinto. MODIS (1 km) mira desde 2000; VIIRS (375 m) desde 2012 y ve más detalle, así que detecta más focos sobre el mismo fuego. Por eso NINA nunca suma sus conteos: compara siempre dentro de un mismo observador.',
    ),
  },
  {
    target: '.coordinates-button',
    title: tr('3 · Your own area', '3 · Tu propia área'),
    body: tr(
      'Interested in a watershed, a protected area or your district? Type coordinates or draw a polygon on the map with the pencil on the right.',
      '¿Te interesa una cuenca, un área protegida o tu distrito? Escribe coordenadas o dibuja un polígono sobre el mapa con el lápiz de la derecha.',
    ),
  },
  {
    target: '.atlas-stage',
    title: tr('4 · The map', '4 · El mapa'),
    body: tr(
      'Each red cloud groups the detections of the chosen month. Drag to rotate the globe and use the wheel to zoom. Click a point to see its date, its fire radiative power (FRP, in megawatts) and the product confidence.',
      'Cada nube roja agrupa detecciones del mes elegido. Arrastra para girar el globo y usa la rueda para acercarte. Haz clic en un punto para ver su fecha, su potencia radiativa (FRP, en megavatios) y la confianza del producto.',
    ),
  },
  {
    target: '.map-tools',
    title: tr('5 · Map tools', '5 · Herramientas del mapa'),
    body: tr(
      'Switch between 3D globe and 2D map, re-center your selection, zoom in or out and draw an area.',
      'Cambia entre globo 3D y mapa 2D, vuelve a centrar tu selección, acércate o aléjate y dibuja un área.',
    ),
  },
  {
    target: '.month-axis',
    title: tr('6 · When?', '6 · ¿Cuándo?'),
    body: tr(
      'Pick the month. An empty mark means there is no data for that period, which is not the same as zero hotspots. NINA never paints a gap as “no activity”.',
      'Elige el mes. Una marca vacía significa que no hay datos para ese periodo, que no es lo mismo que cero focos. NINA nunca pinta un hueco como «sin actividad».',
    ),
  },
  {
    target: '.map-evidence',
    title: tr('7 · Is it an unusual month?', '7 · ¿Es un mes inusual?'),
    body: tr(
      '“Review evidence” compares the month with the median of the same month in other years from the same observer and shows how many years support the comparison.',
      '«Revisar evidencia» compara el mes con la mediana de ese mismo mes en otros años del mismo observador e indica cuántos años sustentan la comparación.',
    ),
  },
  {
    target: '.site-header nav',
    title: tr('8 · More views', '8 · Más vistas'),
    body: tr(
      '“Calendar” shows years by months so you can discover the fire season of a place. “Lab” puts two observers side by side to see how much the signal changes with the satellite.',
      '«Calendario» muestra años por meses para descubrir la temporada de fuego de un lugar. «Laboratorio» pone dos observadores lado a lado para ver cuánto cambia la señal según el satélite.',
    ),
  },
  {
    target: '.time-export',
    title: tr('9 · Take the data with you', '9 · Llévate los datos'),
    body: tr(
      'Export hotspots and aggregates as CSV, with the NASA FIRMS citation and the filters used. Remember: these are historical-context data, not for tactical or local-scale decisions.',
      'Exporta los focos y los agregados en CSV, con la cita de NASA FIRMS y los filtros usados. Recuerda: son datos de contexto histórico, no para decisiones tácticas o a escala local.',
    ),
  },
]

export default function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0),
    [rect, setRect] = useState<DOMRect | null>(null),
    card = useRef<HTMLDivElement>(null),
    [pos, setPos] = useState({ top: 0, left: 0 })
  const STEPS = steps(),
    step = STEPS[i],
    last = i === STEPS.length - 1
  useEffect(() => {
    const el = step.target ? document.querySelector(step.target) : null
    el?.scrollIntoView({ block: 'center', behavior: 'instant' })
    card.current?.focus()
    const measure = () => setRect(el ? el.getBoundingClientRect() : null)
    measure()
    addEventListener('resize', measure)
    addEventListener('scroll', measure, true)
    return () => {
      removeEventListener('resize', measure)
      removeEventListener('scroll', measure, true)
    }
  }, [i])
  useLayoutEffect(() => {
    const c = card.current
    if (!c) return
    const w = c.offsetWidth,
      h = c.offsetHeight,
      m = 16
    if (!rect) {
      setPos({ top: (innerHeight - h) / 2, left: (innerWidth - w) / 2 })
      return
    }
    // Below the target if it fits; otherwise above; if the target fills most of the screen, inside it.
    let top = rect.bottom + 14
    if (top + h > innerHeight - m) top = rect.top - h - 14
    if (top < m) top = Math.min(innerHeight - h - m, rect.top + 24)
    const left = Math.min(Math.max(m, rect.left + rect.width / 2 - w / 2), innerWidth - w - m)
    setPos({ top, left })
  }, [rect, i])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' && !last) setI(i + 1)
      else if (e.key === 'ArrowLeft' && i) setI(i - 1)
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [i, last, onClose])
  const pad = 6
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? (
        <div
          className="tour-spot"
          style={{
            top: rect.top - pad,
            left: rect.left - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
          }}
        />
      ) : (
        <div className="tour-veil" />
      )}
      <div ref={card} tabIndex={-1} className="tour-card" style={pos}>
        <div className="tour-top">
          <span>
            {i + 1} / {STEPS.length}
          </span>
          <button onClick={onClose} aria-label={tr('Close guide', 'Cerrar guía')}>
            <X size={16} />
          </button>
        </div>
        <h2 id="tour-title">{step.title}</h2>
        <p>{step.body}</p>
        <div className="tour-progress" aria-hidden="true">
          {STEPS.map((_, k) => (
            <i key={k} className={k <= i ? 'on' : ''} />
          ))}
        </div>
        <div className="tour-actions">
          <button onClick={() => setI(i - 1)} disabled={!i}>
            <ArrowLeft size={15} />
            {tr('Back', 'Anterior')}
          </button>
          {last ? (
            <button className="tour-next" onClick={onClose}>
              {tr('Start exploring', 'Empezar a explorar')}
            </button>
          ) : (
            <button className="tour-next" onClick={() => setI(i + 1)}>
              {tr('Next', 'Siguiente')}
              <ArrowRight size={15} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
