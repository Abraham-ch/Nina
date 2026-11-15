import { useEffect, useRef, useState } from 'react'

import { locale, tr } from '../i18n'
import LangSwitch from '../LangSwitch'
import Evidence, { day, share, title, type PeruEvidence, type WorldEvidence } from './Evidence'
import Team from './Team'
import { createScene, weekLabel, type Countries, type LandingData, type Week } from './scene'

import './landing.css'

const fmt = { format: (n: number) => n.toLocaleString(locale()) }
const clamp = (v: number) => Math.min(1, Math.max(0, v))
const pct = (v: number) => `${Math.round(v * 100)} %`

// Day of the emergency decree for Amazonas, San Martín and Ucayali (DS 097-2024-PCM, docs/PROBLEM.md §1.2).
const DECREE = '2024-09-18'
const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000)

/** Indicators from the harmonized archive (docs/PROBLEM.md, read from peru-evidence.json): what the record makes possible. */
function indicators(e: PeruEvidence) {
  const peru = e.replay_2024.find((r) => r.label === 'Peru')
  const since = peru?.above_previous_max_continuously_since ?? null
  const top = [...e.detected_vs_reported.departments_2024]
    .sort((a, b) => b.detected_share - a.detected_share)
    .slice(0, 3)
  return {
    rank: e.september_2024.rank_2003_2025,
    years: e.september_2024.years_compared,
    anomaly: Math.round(e.september_2024.anomaly_vs_median_snpp_only_2012_2023),
    since,
    lead: since ? daysBetween(since, DECREE) : null,
    top: top.map((d) => title(d.department)),
    topShare: top.reduce((s, d) => s + d.detected_share, 0),
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
  const [evidence, setEvidence] = useState<PeruEvidence | null>(null)
  const [world, setWorld] = useState<WorldEvidence | null>(null)
  const [week, setWeek] = useState<Week | null>(null)

  useEffect(() => {
    let scene: { destroy(): void } | undefined,
      alive = true
    Promise.all([
      fetch('/assets/countries.geojson').then((r) => r.json() as Promise<Countries>),
      fetch('/assets/landing-peru.json')
        .then((r) => (r.ok ? (r.json() as Promise<LandingData>) : null))
        .catch(() => null),
      fetch('/assets/peru-evidence.json')
        .then((r) => (r.ok ? (r.json() as Promise<PeruEvidence>) : null))
        .catch(() => null),
      fetch('/assets/world-evidence.json')
        .then((r) => (r.ok ? (r.json() as Promise<WorldEvidence>) : null))
        .catch(() => null),
    ]).then(([countries, peruData, peruEvidence, worldEvidence]) => {
      if (!alive || !canvas.current) return
      setData(peruData)
      setEvidence(peruEvidence)
      setWorld(worldEvidence)
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
          <LangSwitch className="on-dark landing-lang" />
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
        evidence &&
        (() => {
          const k = indicators(evidence),
            night = data.night / data.detections
          const items = [
            {
              figure: tr(`#${k.rank}`, `${k.rank}.º`),
              sub: tr(`of ${k.years} Septembers`, `de ${k.years} septiembres`),
              title: tr(
                'September 2024, measured against every September since 2003',
                'septiembre de 2024, medido frente a cada septiembre desde 2003',
              ),
              q: tr('When to prevent?', '¿Cuándo prevenir?'),
              body: tr(
                'One consistent record across satellites places each season against its own history, so campaigns, burning restrictions and brigades can be planned before the peak.',
                'Un registro coherente entre satélites sitúa cada temporada frente a su propia historia, para planificar campañas, restricciones de quemas y brigadas antes del pico.',
              ),
            },
            {
              figure: String(k.lead ?? '—'),
              sub: tr('days ahead', 'días antes'),
              title: tr(
                k.since
                  ? `from ${day(k.since)} the season stood above every year since 2003, before the 18 September decree`
                  : 'before the 18 September decree',
                k.since
                  ? `desde el ${day(k.since)} la temporada superaba a todos los años desde 2003, antes del decreto del 18 de septiembre`
                  : 'antes del decreto del 18 de septiembre',
              ),
              q: tr('How early can we know?', '¿Con cuánta anticipación se puede saber?'),
              body: tr(
                'Comparing the last 14 days with the same dates in history gives an objective, shareable signal to escalate in time.',
                'Comparar los últimos 14 días con las mismas fechas de la historia da una señal objetiva y compartible para escalar a tiempo.',
              ),
            },
            {
              figure: share(k.topShare),
              title: tr(
                `of the activity detected in 2024, in ${k.top.join(', ')}`,
                `de la actividad detectada en 2024, en ${k.top.join(', ')}`,
              ),
              q: tr('Where to prioritize?', '¿Dónde priorizar?'),
              body: tr(
                'Detected activity shows where prevention, environmental education and brigades reach the most fire, wherever it happens.',
                'La actividad detectada muestra dónde la prevención, la educación ambiental y las brigadas alcanzan más fuego, ocurra donde ocurra.',
              ),
            },
            {
              figure: `+${k.anomaly} %`,
              title: tr(
                'September 2024 above the 2012–2023 median, same instrument',
                'septiembre de 2024 sobre la mediana 2012–2023, mismo instrumento',
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
                    `Indicators from the harmonized MODIS + VIIRS archive for Peru (method ${evidence.method_version}, experimental), unit: VIIRS-equivalent active cell-days; a retrospective reading, not a tested alert. The animation behind them shows one year of real VIIRS NOAA-20 detections (${data.first_date} → ${data.last_date}, ${fmt.format(data.detections)} detections, ${pct(night)} at night). They are context indicators for planning, not for tactical response.`,
                    `Indicadores del archivo armonizado MODIS + VIIRS del Perú (método ${evidence.method_version}, experimental), en celdas-día activas equivalentes VIIRS; es una lectura retrospectiva, no una alerta probada. La animación de fondo muestra un año de detecciones reales VIIRS NOAA-20 (${data.first_date} → ${data.last_date}, ${fmt.format(data.detections)} detecciones, el ${pct(night)} nocturnas). Son indicadores de contexto para planificar, no de respuesta táctica.`,
                  )}
                </p>
              </section>
            </>
          )
        })()}

      <Evidence e={evidence} w={world} />

      <Team />

      <section
        ref={data && evidence ? undefined : outro}
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
