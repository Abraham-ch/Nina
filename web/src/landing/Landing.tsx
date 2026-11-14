import { useEffect, useRef, useState } from 'react'

import { locale, tr } from '../i18n'
import LangSwitch from '../LangSwitch'
import { createScene, weekLabel, type Countries, type LandingData, type Week } from './scene'

import './landing.css'

const fmt = { format: (n: number) => n.toLocaleString(locale()) }
const clamp = (v: number) => Math.min(1, Math.max(0, v))
const pct = (v: number) => `${Math.round(v * 100)} %`

/** Indicators derived only from the real summary (one observer, one period); nothing is estimated or extrapolated. */
function indicators(d: LandingData) {
  const full = d.weeks.filter((w) => !w.partial),
    total = d.detections
  const season =
    d.weeks
      .filter((w) => {
        const m = new Date(w.week + 'T00:00:00Z').getUTCMonth()
        return m >= 6 && m <= 9
      })
      .reduce((s, w) => s + w.count, 0) / total
  const sorted = full.map((w) => w.count).sort((a, b) => b - a)
  let acc = 0,
    half = 0
  while (acc < total / 2 && half < sorted.length) acc += sorted[half++]
  const median = [...sorted].reverse()[Math.floor(sorted.length / 2)] || 1
  const top = d.departments.slice(0, 3)
  return {
    season,
    half,
    weeks: full.length,
    ratio: d.peak_count / median,
    night: d.night / total,
    top,
    topShare: top.reduce((s, x) => s + x.count, 0) / total,
    regions: d.departments.length,
  }
}

/** Rolling digit counter: each digit spins two full turns to its value; when deactivated it returns to 0. */
function Roll({ value, active }: { value: string; active: boolean }) {
  let digit = 0
  return (
    <span className="roll">
      <span className="sr-only">{value}</span>
      {[...value].map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={i} className="roll-digit" aria-hidden="true">
            <span
              style={{
                transform: `translateY(-${((active ? 20 + Number(ch) : 0) * 100) / 30}%)`,
                transitionDelay: `${digit++ * 90}ms`,
              }}
            >
              {Array.from({ length: 30 }, (_, k) => (
                <span key={k}>{k % 10}</span>
              ))}
            </span>
          </span>
        ) : (
          <span key={i} aria-hidden="true">
            {ch}
          </span>
        ),
      )}
    </span>
  )
}

export default function Landing({ onEnter }: { onEnter: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const peru = useRef<HTMLElement>(null),
    impact = useRef<HTMLElement>(null),
    outro = useRef<HTMLElement>(null) // outro: the scene dims from here
  const [focus, setFocus] = useState(-1)
  const focusRef = useRef(-1)
  const [data, setData] = useState<LandingData | null>(null)
  const [week, setWeek] = useState<Week | null>(null)

  useEffect(() => {
    let scene: { destroy(): void } | undefined,
      alive = true
    Promise.all([
      fetch('/assets/countries.geojson').then((r) => r.json() as Promise<Countries>),
      fetch('/assets/landing-peru.json')
        .then((r) => (r.ok ? (r.json() as Promise<LandingData>) : null))
        .catch(() => null),
    ]).then(([countries, peruData]) => {
      if (!alive || !canvas.current) return
      setData(peruData)
      scene = createScene(canvas.current, countries, peruData, {
        // World → Peru while the Peru section scrolls up; hotspots appear on arrival; the closing section dims the scene.
        progress() {
          const h = innerHeight,
            p = peru.current?.getBoundingClientRect().top ?? h,
            o = outro.current?.getBoundingClientRect().top ?? h
          const morph = clamp(1 - p / (h * 1.6))
          // Third scene: Peru is centered when the section enters; every 85 vh of scroll activates the next indicator.
          const t = impact.current?.getBoundingClientRect().top ?? h,
            stage = clamp(1 - t / (h * 0.6))
          const f = t > h * 0.12 ? -1 : Math.min(3, Math.floor((h * 0.12 - t) / (h * 0.85)))
          if (f !== focusRef.current) {
            focusRef.current = f
            setFocus(f)
          }
          return {
            morph,
            fire: clamp((morph - 0.82) / 0.18),
            dim: clamp(1 - o / (h * 0.8)),
            stage,
            focus: f,
          }
        },
        onWeek: (w) => setWeek(w),
      })
    })
    return () => {
      alive = false
      scene?.destroy()
    }
  }, [])

  return (
    <div className="landing">
      <canvas ref={canvas} className="landing-canvas" aria-hidden="true" />
      <header className="landing-header">
        <span className="landing-brand">
          NINA
          <span>{tr('The memory of fire', 'La memoria del fuego')}</span>
        </span>
        <div className="landing-header-actions">
          <LangSwitch className="on-dark" />
          <button className="landing-enter" onClick={onEnter}>
            {tr('Open the atlas', 'Abrir el atlas')}
          </button>
        </div>
      </header>

      <section className="landing-hero" aria-labelledby="landing-title">
        <p className="landing-kicker">
          {tr(
            'NASA FIRMS active fires · MODIS and VIIRS',
            'Focos activos NASA FIRMS · MODIS y VIIRS',
          )}
        </p>
        <h1 id="landing-title">
          {tr('Every dot is a place on the planet.', 'Cada punto es un lugar del planeta.')}
          <br />
          {tr('Some are burning.', 'Algunos arden.')}
        </h1>
        <p>
          {tr(
            'A chart the size of the world: longitude on top, latitude on the left, kilometres to the equator on the right. Scroll down and the planet shrinks into Peru, where thermal detections light up week by week.',
            'Una gráfica del tamaño del mundo: longitud arriba, latitud a la izquierda, kilómetros al ecuador a la derecha. Baja y el planeta se contrae hasta el Perú, donde se encienden las detecciones térmicas semana a semana.',
          )}
        </p>
        <div className="landing-actions">
          <button className="landing-cta" onClick={onEnter}>
            {tr('Explore the atlas', 'Explorar el atlas')}
          </button>
          <a href="#landing-peru" className="landing-more">
            {tr('See Peru ↓', 'Ver el Perú ↓')}
          </a>
        </div>
      </section>

      <div className="landing-travel" aria-hidden="true" />

      <section
        ref={peru}
        id="landing-peru"
        className="landing-peru"
        aria-labelledby="landing-peru-title"
      >
        <div className="landing-panel">
          <p className="landing-kicker">
            {tr('Peru', 'Perú')} ·{' '}
            {data ? `${data.first_date} → ${data.last_date}` : tr('loading data', 'cargando datos')}
          </p>
          <h2 id="landing-peru-title">
            {tr('A year of heat seen from orbit', 'Un año de calor visto desde órbita')}
          </h2>
          {data ? (
            <>
              <dl className="landing-stats">
                <div>
                  <dt>{tr('Detections', 'Detecciones')}</dt>
                  <dd>{fmt.format(data.detections)}</dd>
                </div>
                <div>
                  <dt>{tr('Peak week', 'Semana pico')}</dt>
                  <dd>{weekLabel(data.peak_week)}</dd>
                </div>
                <div>
                  <dt>{tr('At the peak', 'En el pico')}</dt>
                  <dd>{fmt.format(data.peak_count)}</dd>
                </div>
              </dl>
              <p className="landing-live" aria-live="off">
                {week ? (
                  <>
                    {tr('Week of', 'Semana del')} <strong>{weekLabel(week.week)}</strong> ·{' '}
                    {fmt.format(week.count)} {tr('detections', 'detecciones')}
                    {week.partial ? tr(' (incomplete week)', ' (semana incompleta)') : ''}
                  </>
                ) : (
                  ' '
                )}
              </p>
              <p className="landing-note">
                {tr(
                  `Each glow is a 0.1° cell with detections from a single observer, VIIRS NOAA-20 (${data.platform}), aggregated by UTC week. They are thermal pixels, not individual fires. The bottom bar measures the real weekly total.`,
                  `Cada brillo es una celda de 0,1° con detecciones de un solo observador, VIIRS NOAA-20 (${data.platform}), agregadas por semana UTC. Son píxeles térmicos, no incendios individuales. La barra inferior mide el total semanal real.`,
                )}
              </p>
            </>
          ) : (
            <p className="landing-note">
              {tr(
                'The Peru summary was not found; generate',
                'No se encontró el resumen del Perú; genera',
              )}{' '}
              <code>web/public/assets/landing-peru.json</code> {tr('with', 'con')}{' '}
              <code>scripts/build_landing_data.py</code>.
            </p>
          )}
        </div>
      </section>

      {data &&
        (() => {
          const k = indicators(data)
          const items = [
            {
              figure: pct(k.season),
              title: tr(
                'of detections fall between July and October',
                'de las detecciones cae entre julio y octubre',
              ),
              q: tr('When to prevent?', '¿Cuándo prevenir?'),
              body: tr(
                'A seasonal calendar to schedule campaigns, burning restrictions and brigade readiness before the peak, not during it.',
                'Un calendario estacional para programar campañas, restricciones de quemas y preparación de brigadas antes del pico, no durante.',
              ),
            },
            {
              figure: String(k.half),
              sub: tr(`of ${k.weeks} weeks`, `de ${k.weeks} semanas`),
              title: tr('hold half of all activity', 'concentran la mitad de toda la actividad'),
              q: tr('How long is the critical window?', '¿Cuánto dura la ventana crítica?'),
              body: tr(
                'Risk piles up in a few weeks: that is where concentrating surveillance and risk communication pays off most.',
                'El riesgo se acumula en pocas semanas: ahí rinde más concentrar vigilancia y comunicación de riesgo.',
              ),
            },
            {
              figure: pct(k.topShare),
              title: tr(
                `in ${k.top.map((t) => t.name).join(', ')}`,
                `en ${k.top.map((t) => t.name).join(', ')}`,
              ),
              q: tr('Where to prioritize?', '¿Dónde priorizar?'),
              body: tr(
                `Of ${k.regions} regions with detections, three hold this share: an objective basis to guide environmental education and preventive investment.`,
                `De ${k.regions} regiones con detecciones, tres reúnen esta proporción: una base objetiva para orientar educación ambiental e inversión preventiva.`,
              ),
            },
            {
              figure: `×${k.ratio.toFixed(0)}`,
              title: tr(
                'the peak week against the typical week',
                'la semana pico frente a la semana típica',
              ),
              q: tr('How much does the pressure grow?', '¿Cuánto crece la presión?'),
              body: tr(
                'It sizes the capacity needed in high season, including smoke-related care in public health.',
                'Dimensiona la capacidad que hace falta en temporada alta, incluida la atención por humo en salud pública.',
              ),
            },
          ]
          const goTo = (i: number) => {
            const top = impact.current ? impact.current.getBoundingClientRect().top + scrollY : 0
            scrollTo({
              top: top + innerHeight * (0.12 + 0.85 * i + 0.3),
              behavior: 'smooth',
            })
          }
          return (
            <>
              <section
                ref={impact}
                className="landing-impact"
                aria-labelledby="landing-impact-title"
              >
                <div className="landing-stage">
                  <div className="landing-stage-head">
                    <p className="landing-kicker">
                      {tr('What these data help answer', 'Lo que estos datos permiten resolver')}
                    </p>
                    <h2 id="landing-impact-title">
                      {tr(
                        'From a thermal pixel to a prevention decision',
                        'Del píxel térmico a una decisión de prevención',
                      )}
                    </h2>
                  </div>
                  {items.map((it, i) => (
                    <button
                      key={i}
                      type="button"
                      aria-pressed={focus === i}
                      onClick={() => goTo(i)}
                      className={`landing-ind landing-ind-${i}${focus === i ? ' on' : ''}${focus > i ? ' seen' : ''}`}
                    >
                      <span className="landing-figure">
                        <Roll value={it.figure} active={focus >= i} />
                        {it.sub && <small>{it.sub}</small>}
                      </span>
                      <strong>{it.title}</strong>
                      <span className="landing-ind-body">
                        <em>{it.q}</em> {it.body}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
              <section
                ref={outro}
                className="landing-why"
                aria-label={tr('Who it is for and scope', 'Para quién y alcance')}
              >
                <div className="landing-impact-grid">
                  <div>
                    <h3>{tr('Who it is for', 'Para quién')}</h3>
                    <ul className="landing-who">
                      <li>
                        <strong>
                          {tr(
                            'Risk managers and regional governments',
                            'Gestores de riesgo y gobiernos regionales',
                          )}
                        </strong>{' '}
                        {tr(
                          'preventive planning and territorial prioritization.',
                          'planificación preventiva y priorización territorial.',
                        )}
                      </li>
                      <li>
                        <strong>
                          {tr(
                            'Rural communities and producers',
                            'Comunidades y productores rurales',
                          )}
                        </strong>{' '}
                        {tr(
                          'a local calendar to avoid burning in the critical season.',
                          'calendario local para evitar quemas en la temporada crítica.',
                        )}
                      </li>
                      <li>
                        <strong>
                          {tr('Public health and schools', 'Salud pública y escuelas')}
                        </strong>{' '}
                        {tr(
                          'anticipate the smokiest weeks.',
                          'anticipar las semanas con más humo.',
                        )}
                      </li>
                      <li>
                        <strong>
                          {tr(
                            'Journalism, science and citizens',
                            'Periodismo, ciencia y ciudadanía',
                          )}
                        </strong>{' '}
                        {tr(
                          'verifiable, cited and downloadable evidence.',
                          'evidencia verificable, citada y descargable.',
                        )}
                      </li>
                    </ul>
                  </div>
                  <div>
                    <h3>
                      {tr('Sustainable Development Goals', 'Objetivos de Desarrollo Sostenible')}
                    </h3>
                    <ul className="landing-ods">
                      <li>
                        <b>13</b>
                        {tr('Climate action', 'Acción por el clima')}
                      </li>
                      <li>
                        <b>15</b>
                        {tr('Life on land', 'Vida de ecosistemas terrestres')}
                      </li>
                      <li>
                        <b>3</b>
                        {tr('Good health and well-being', 'Salud y bienestar')}
                      </li>
                      <li>
                        <b>11</b>
                        {tr(
                          'Sustainable cities and communities',
                          'Ciudades y comunidades sostenibles',
                        )}
                      </li>
                    </ul>
                  </div>
                </div>
                <p className="landing-caveat">
                  {tr(
                    `Indicators computed from the ${fmt.format(data.detections)} real detections in Peru. Scope: one year (${data.first_date} → ${data.last_date}) and a single observer (VIIRS NOAA-20); ${pct(k.night)} of the detections were at night. They are context indicators for planning, not for tactical response. Comparing years and detecting anomalies requires the harmonized MODIS + VIIRS historical archive, under development in NINA.`,
                    `Indicadores calculados con las ${fmt.format(data.detections)} detecciones reales del Perú. Alcance: un año (${data.first_date} → ${data.last_date}) y un solo observador (VIIRS NOAA-20); el ${pct(k.night)} de las detecciones fue nocturno. Son indicadores de contexto para planificar, no de respuesta táctica. Comparar años y detectar anomalías requiere el archivo histórico armonizado MODIS + VIIRS, en desarrollo en NINA.`,
                  )}
                </p>
              </section>
            </>
          )
        })()}

      <section
        ref={data ? undefined : outro}
        className="landing-outro"
        aria-labelledby="landing-outro-title"
      >
        <h2 id="landing-outro-title">
          {tr(
            'The memory of fire, by territory and by month',
            'La memoria del fuego, por territorio y por mes',
          )}
        </h2>
        <ul className="landing-cards">
          <li>
            <strong>Atlas</strong>
            <span>
              {tr(
                'Pick a country, a Peruvian region or draw a polygon and browse its hotspots on the globe.',
                'Elige un país, una región del Perú o dibuja un polígono y recorre sus focos sobre el globo.',
              )}
            </span>
          </li>
          <li>
            <strong>{tr('Calendar', 'Calendario')}</strong>
            <span>
              {tr(
                'Years by months: compare a season with its reference. A gap is never painted as zero.',
                'Años por meses: compara una temporada con su referencia. Un hueco nunca se pinta como cero.',
              )}
            </span>
          </li>
          <li>
            <strong>{tr('Lab', 'Laboratorio')}</strong>
            <span>
              {tr(
                'MODIS and VIIRS always identified; the cross-sensor calibration is exploratory.',
                'MODIS y VIIRS siempre identificados; la calibración entre sensores es exploratoria.',
              )}
            </span>
          </li>
        </ul>
        <button className="landing-cta" onClick={onEnter}>
          {tr('Explore the atlas', 'Explorar el atlas')}
        </button>
        <footer className="landing-footer">
          <p>
            {tr(
              "We acknowledge the use of data and imagery from NASA's Fire Information for Resource Management System (FIRMS) (https://www.earthdata.nasa.gov/data/tools/firms), part of NASA's Earth Science Data and Information System (ESDIS). Boundaries: geoBoundaries and Natural Earth.",
              'Reconocemos el uso de datos e imágenes del Fire Information for Resource Management System (FIRMS) de la NASA (https://www.earthdata.nasa.gov/data/tools/firms), parte del Earth Science Data and Information System (ESDIS) de la NASA. Contornos: geoBoundaries y Natural Earth.',
            )}
          </p>
          <p>
            {tr(
              'Because of their spatial resolution, FIRMS does not recommend these data for tactical or local-scale decisions. NINA is a tool for historical context.',
              'Por su resolución espacial, FIRMS no recomienda usar estos datos para decisiones tácticas o a escala local. NINA es una herramienta de contexto histórico.',
            )}{' '}
            <a
              href="https://www.earthdata.nasa.gov/data/tools/firms"
              target="_blank"
              rel="noreferrer"
            >
              {tr('FIRMS disclaimer', 'Descargo de responsabilidad de FIRMS')}
            </a>
            .
          </p>
        </footer>
      </section>
    </div>
  )
}
