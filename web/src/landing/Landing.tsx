import {useEffect, useRef, useState} from 'react';
import {createScene, weekLabel, type Countries, type LandingData, type Week} from './scene';
import './landing.css';

const fmt = new Intl.NumberFormat('es-PE');
const clamp = (v: number) => Math.min(1, Math.max(0, v));
const pct = (v: number) => `${Math.round(v * 100)} %`;

/** Indicadores derivados solo del resumen real (un observador, un período); nada se estima ni se extrapola. */
function indicators(d: LandingData) {
  const full = d.weeks.filter(w => !w.partial), total = d.detections;
  const season = d.weeks.filter(w => { const m = new Date(w.week + 'T00:00:00Z').getUTCMonth(); return m >= 6 && m <= 9; })
    .reduce((s, w) => s + w.count, 0) / total;
  const sorted = full.map(w => w.count).sort((a, b) => b - a);
  let acc = 0, half = 0;
  while (acc < total / 2 && half < sorted.length) acc += sorted[half++];
  const median = [...sorted].reverse()[Math.floor(sorted.length / 2)] || 1;
  const top = d.departments.slice(0, 3);
  return {
    season, half, weeks: full.length, ratio: d.peak_count / median, night: d.night / total,
    top, topShare: top.reduce((s, x) => s + x.count, 0) / total, regions: d.departments.length,
  };
}

/** Contador de dígitos rodantes: cada cifra gira dos vueltas completas hasta su valor; al desactivarse vuelve a 0. */
function Roll({value, active}: {value: string; active: boolean}) {
  let digit = 0;
  return <span className="roll">
    <span className="sr-only">{value}</span>
    {[...value].map((ch, i) => /\d/.test(ch)
      ? <span key={i} className="roll-digit" aria-hidden="true">
          <span style={{transform: `translateY(-${((active ? 20 + Number(ch) : 0) * 100) / 30}%)`, transitionDelay: `${digit++ * 90}ms`}}>
            {Array.from({length: 30}, (_, k) => <span key={k}>{k % 10}</span>)}
          </span>
        </span>
      : <span key={i} aria-hidden="true">{ch}</span>)}
  </span>;
}

export default function Landing({onEnter}: {onEnter: () => void}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const peru = useRef<HTMLElement>(null), impact = useRef<HTMLElement>(null), outro = useRef<HTMLElement>(null); // outro: desde aquí se atenúa
  const [focus, setFocus] = useState(-1);
  const focusRef = useRef(-1);
  const [data, setData] = useState<LandingData | null>(null);
  const [week, setWeek] = useState<Week | null>(null);
  // Respeta "reducir movimiento" del sistema, pero deja que la persona lo active desde la portada.
  const [animate, setAnimate] = useState(() => !matchMedia('(prefers-reduced-motion: reduce)').matches);
  const animateRef = useRef(animate);
  animateRef.current = animate;

  useEffect(() => {
    let scene: {destroy(): void} | undefined, alive = true;
    Promise.all([
      fetch('/assets/countries.geojson').then(r => r.json() as Promise<Countries>),
      fetch('/assets/landing-peru.json').then(r => r.ok ? r.json() as Promise<LandingData> : null).catch(() => null),
    ]).then(([countries, peruData]) => {
      if (!alive || !canvas.current) return;
      setData(peruData);
      scene = createScene(canvas.current, countries, peruData, {
        // Mundo → Perú mientras la sección del Perú sube; los focos aparecen al llegar; el cierre atenúa la escena.
        progress() {
          const h = innerHeight, p = peru.current?.getBoundingClientRect().top ?? h, o = outro.current?.getBoundingClientRect().top ?? h;
          const morph = clamp(1 - p / (h * 1.6));
          // Tercera escena: el Perú se centra al entrar la sección; cada 85 vh de scroll activa el siguiente indicador.
          const t = impact.current?.getBoundingClientRect().top ?? h, stage = clamp(1 - t / (h * .6));
          const f = t > h * .12 ? -1 : Math.min(3, Math.floor((h * .12 - t) / (h * .85)));
          if (f !== focusRef.current) { focusRef.current = f; setFocus(f); }
          return {morph, fire: clamp((morph - .82) / .18), dim: clamp(1 - o / (h * .8)), stage, focus: f};
        },
        onWeek: w => setWeek(w),
        animate: () => animateRef.current,
      });
    });
    return () => { alive = false; scene?.destroy(); };
  }, []);

  return <div className={`landing${animate ? '' : ' still'}`}>
    <canvas ref={canvas} className="landing-canvas" aria-hidden="true"/>
    <header className="landing-header">
      <span className="landing-brand">NINA<span>La memoria del fuego</span></span>
      <div className="landing-header-actions">
        <button className="landing-enter" aria-pressed={animate} onClick={() => setAnimate(a => !a)}>
          {animate ? 'Pausar animación' : 'Animar'}</button>
        <button className="landing-enter" onClick={onEnter}>Abrir el atlas</button>
      </div>
    </header>

    <section className="landing-hero" aria-labelledby="landing-title">
      <p className="landing-kicker">Focos activos NASA FIRMS · MODIS y VIIRS</p>
      <h1 id="landing-title">Cada punto es un lugar del planeta.<br/>Algunos arden.</h1>
      <p>Una gráfica del tamaño del mundo: longitud arriba, latitud a la izquierda, kilómetros al ecuador a la derecha.
        Baja y el planeta se contrae hasta el Perú, donde se encienden las detecciones térmicas semana a semana.</p>
      <div className="landing-actions">
        <button className="landing-cta" onClick={onEnter}>Explorar el atlas</button>
        <a href="#landing-peru" className="landing-more">Ver el Perú ↓</a>
      </div>
    </section>

    <div className="landing-travel" aria-hidden="true"/>

    <section ref={peru} id="landing-peru" className="landing-peru" aria-labelledby="landing-peru-title">
      <div className="landing-panel">
        <p className="landing-kicker">Perú · {data ? `${data.first_date} → ${data.last_date}` : 'cargando datos'}</p>
        <h2 id="landing-peru-title">Un año de calor visto desde órbita</h2>
        {data ? <>
          <dl className="landing-stats">
            <div><dt>Detecciones</dt><dd>{fmt.format(data.detections)}</dd></div>
            <div><dt>Semana pico</dt><dd>{weekLabel(data.peak_week)}</dd></div>
            <div><dt>En el pico</dt><dd>{fmt.format(data.peak_count)}</dd></div>
          </dl>
          <p className="landing-live" aria-live="off">
            {week ? <>Semana del <strong>{weekLabel(week.week)}</strong> · {fmt.format(week.count)} detecciones{week.partial ? ' (semana incompleta)' : ''}</> : ' '}
          </p>
          <p className="landing-note">Cada brillo es una celda de 0,1° con detecciones de un solo observador, VIIRS NOAA-20
            ({data.platform}), agregadas por semana UTC. Son píxeles térmicos, no incendios individuales. La barra inferior
            mide el total semanal real.</p>
        </> : <p className="landing-note">No se encontró el resumen del Perú; genera <code>web/public/assets/landing-peru.json</code> con <code>scripts/build_landing_data.py</code>.</p>}
      </div>
    </section>

    {data && (() => {
      const k = indicators(data);
      const items = [
        {figure: pct(k.season), title: 'de las detecciones cae entre julio y octubre', q: '¿Cuándo prevenir?',
          body: 'Un calendario estacional para programar campañas, restricciones de quemas y preparación de brigadas antes del pico, no durante.'},
        {figure: String(k.half), sub: `de ${k.weeks} semanas`, title: 'concentran la mitad de toda la actividad', q: '¿Cuánto dura la ventana crítica?',
          body: 'El riesgo se acumula en pocas semanas: ahí rinde más concentrar vigilancia y comunicación de riesgo.'},
        {figure: pct(k.topShare), title: `en ${k.top.map(t => t.name).join(', ')}`, q: '¿Dónde priorizar?',
          body: `De ${k.regions} regiones con detecciones, tres reúnen esta proporción: una base objetiva para orientar educación ambiental e inversión preventiva.`},
        {figure: `×${k.ratio.toFixed(0)}`, title: 'la semana pico frente a la semana típica', q: '¿Cuánto crece la presión?',
          body: 'Dimensiona la capacidad que hace falta en temporada alta, incluida la atención por humo en salud pública.'},
      ];
      const goTo = (i: number) => {
        const top = impact.current ? impact.current.getBoundingClientRect().top + scrollY : 0;
        scrollTo({top: top + innerHeight * (.12 + .85 * i + .3), behavior: animate ? 'smooth' : 'auto'});
      };
      return <>
        <section ref={impact} className="landing-impact" aria-labelledby="landing-impact-title">
          <div className="landing-stage">
            <div className="landing-stage-head">
              <p className="landing-kicker">Lo que estos datos permiten resolver</p>
              <h2 id="landing-impact-title">Del píxel térmico a una decisión de prevención</h2>
            </div>
            {items.map((it, i) => <button key={i} type="button" aria-pressed={focus === i} onClick={() => goTo(i)}
              className={`landing-ind landing-ind-${i}${focus === i ? ' on' : ''}${focus > i ? ' seen' : ''}`}>
              <span className="landing-figure"><Roll value={it.figure} active={focus >= i}/>{it.sub && <small>{it.sub}</small>}</span>
              <strong>{it.title}</strong>
              <span className="landing-ind-body"><em>{it.q}</em> {it.body}</span>
            </button>)}
          </div>
        </section>
        <section ref={outro} className="landing-why" aria-label="Para quién y alcance">
          <div className="landing-impact-grid">
            <div>
              <h3>Para quién</h3>
              <ul className="landing-who">
                <li><strong>Gestores de riesgo y gobiernos regionales</strong> planificación preventiva y priorización territorial.</li>
                <li><strong>Comunidades y productores rurales</strong> calendario local para evitar quemas en la temporada crítica.</li>
                <li><strong>Salud pública y escuelas</strong> anticipar las semanas con más humo.</li>
                <li><strong>Periodismo, ciencia y ciudadanía</strong> evidencia verificable, citada y descargable.</li>
              </ul>
            </div>
            <div>
              <h3>Objetivos de Desarrollo Sostenible</h3>
              <ul className="landing-ods">
                <li><b>13</b>Acción por el clima</li>
                <li><b>15</b>Vida de ecosistemas terrestres</li>
                <li><b>3</b>Salud y bienestar</li>
                <li><b>11</b>Ciudades y comunidades sostenibles</li>
              </ul>
            </div>
          </div>
          <p className="landing-caveat">Indicadores calculados con las {fmt.format(data.detections)} detecciones reales del Perú. Alcance: un año
            ({data.first_date} → {data.last_date}) y un solo observador (VIIRS NOAA-20); el {pct(k.night)} de las detecciones fue
            nocturno. Son indicadores de contexto para planificar, no de respuesta táctica. Comparar años y detectar anomalías
            requiere el archivo histórico armonizado MODIS + VIIRS, en desarrollo en NINA.</p>
        </section>
      </>;
    })()}

    <section ref={data ? undefined : outro} className="landing-outro" aria-labelledby="landing-outro-title">
      <h2 id="landing-outro-title">La memoria del fuego, por territorio y por mes</h2>
      <ul className="landing-cards">
        <li><strong>Atlas</strong><span>Elige un país, una región del Perú o dibuja un polígono y recorre sus focos sobre el globo.</span></li>
        <li><strong>Calendario</strong><span>Años por meses: compara una temporada con su referencia. Un hueco nunca se pinta como cero.</span></li>
        <li><strong>Laboratorio</strong><span>MODIS y VIIRS siempre identificados; la calibración entre sensores es exploratoria.</span></li>
      </ul>
      <button className="landing-cta" onClick={onEnter}>Explorar el atlas</button>
      <footer className="landing-footer">
        <p>Reconocemos el uso de datos e imágenes del Fire Information for Resource Management System (FIRMS) de la NASA
          (https://www.earthdata.nasa.gov/data/tools/firms), parte del Earth Science Data and Information System (ESDIS) de la NASA.
          Contornos: geoBoundaries y Natural Earth.</p>
        <p>Por su resolución espacial, FIRMS no recomienda usar estos datos para decisiones tácticas o a escala local. NINA es una
          herramienta de contexto histórico. <a href="https://www.earthdata.nasa.gov/data/tools/firms" target="_blank" rel="noreferrer">Descargo de responsabilidad de FIRMS</a>.</p>
      </footer>
    </section>
  </div>;
}
