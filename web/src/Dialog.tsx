import {
  ArrowRight,
  ArrowUpRight,
  Download,
  FileJson,
  Send,
  Share2,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { analysisPath, fmt, months, post, replyFromHarmonized, sourceName } from './api'
import type { Modal } from './App'
import { seasonSVG } from './export'
import { getLang, tr } from './i18n'
import type { Analysis, Geometry, HarmonizedReply, Health, Reply, Selection, User } from './types'
type Props = {
  harmonized: boolean
  modal: Modal
  onModal: (m: Modal) => void
  label: string
  analysis: Analysis | null
  selection: Selection
  health: Health | null
  user: User | null
  onAccount: () => void
  onGeometry: (g: Geometry) => void
  onDraw: () => void
  onShare: () => void
  onError: (s: string) => void
}
// Preset questions: the label follows the interface language; the text sent is the one the assistant engine recognizes.
const PRESETS: [string, string][] = [
  ['What does this period show?', '¿Qué muestra este período?'],
  ['Does the sensor matter?', '¿Influye el sensor?'],
  ['Is the coverage sufficient?', '¿Es suficiente la cobertura?'],
  ['Prepare a report', 'Prepara un informe'],
]
export default function Dialog({
  harmonized,
  modal,
  onModal,
  label,
  analysis,
  selection,
  health,
  user,
  onAccount,
  onGeometry,
  onDraw,
  onShare,
  onError,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null),
    [role, setRole] = useState('gestion'),
    [reply, setReply] = useState<Reply | null>(null),
    [question, setQuestion] = useState(''),
    [asking, setAsking] = useState(false),
    [bounds, setBounds] = useState({
      west: '-78',
      south: '-12',
      east: '-72',
      north: '-7',
    })
  const currentAnalysis = useRef(analysis?.id)
  currentAnalysis.current = analysis?.id
  useEffect(() => {
    if (modal) {
      if (!ref.current?.open) ref.current?.showModal()
    } else ref.current?.close()
  }, [modal])
  useEffect(() => setReply(null), [analysis?.id])
  async function ask(text: string) {
    if (!analysis || asking) return
    setAsking(true)
    const id = analysis.id
    try {
      // The harmonized assistant is deterministic and answers in the interface language.
      const answer = harmonized
        ? replyFromHarmonized(
            await post<HarmonizedReply>('/harmonized/assistant', {
              analysis_id: id,
              question: text,
              language: getLang(),
            }),
          )
        : await post<Reply>('/assistant', {
            analysis_id: id,
            question: text,
            role,
          })
      if (currentAnalysis.current === id) {
        setReply(answer)
        setQuestion('')
      }
    } catch (e) {
      onError(String(e))
    } finally {
      setAsking(false)
    }
  }
  function applyBounds() {
    const { west, south, east, north } = Object.fromEntries(
      Object.entries(bounds).map(([k, v]) => [k, Number(v)]),
    )
    if (
      ![
        -180 <= west && west < east && east <= 180,
        -90 <= south && south < north && north <= 90,
      ].every(Boolean)
    ) {
      onError(
        tr(
          'Enter valid bounds: west < east and south < north, in WGS84.',
          'Introduce límites válidos: oeste < este y sur < norte, en WGS84.',
        ),
      )
      return
    }
    onGeometry({
      type: 'Polygon',
      coordinates: [
        [
          [west, south],
          [east, south],
          [east, north],
          [west, north],
          [west, south],
        ],
      ],
    })
  }
  const selected = analysis?.selected,
    MONTHS = months()
  const puedeExportar = !!user && user.role !== 'visitante'
  const titles = {
    evidence: tr('The analysis record', 'El expediente del análisis'),
    export: tr('Share the investigation', 'Comparte la investigación'),
    explain: tr('Read the signal in context', 'Leer la señal con contexto'),
    area: tr('Define your area', 'Define tu área'),
  }
  return (
    <dialog
      ref={ref}
      className={`nina-dialog ${modal === 'area' ? 'area-dialog' : ''}`}
      onCancel={() => onModal('')}
      onClick={(e) => {
        if (e.target === ref.current) {
          const b = ref.current.getBoundingClientRect()
          if (
            e.clientX < b.left ||
            e.clientX > b.right ||
            e.clientY < b.top ||
            e.clientY > b.bottom
          )
            onModal('')
        }
      }}
      aria-labelledby="dialog-title"
    >
      <div className="dialog-head">
        <div>
          <span className="kicker">{label}</span>
          <h2 id="dialog-title">{titles[modal as Exclude<Modal, ''>] || ''}</h2>
        </div>
        <button onClick={() => onModal('')} aria-label={tr('Close dialog', 'Cerrar diálogo')}>
          <X size={20} />
        </button>
      </div>
      {modal === 'area' ? (
        <div className="dialog-body">
          <p>
            {tr(
              'Enter a rectangle in WGS84 coordinates. You can also draw a polygon on the globe.',
              'Introduce un rectángulo en coordenadas WGS84. También puedes dibujar un polígono sobre el globo.',
            )}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              applyBounds()
            }}
          >
            <div className="bounds-grid">
              {[
                ['west', tr('West (longitude)', 'Oeste (longitud)')],
                ['east', tr('East (longitude)', 'Este (longitud)')],
                ['south', tr('South (latitude)', 'Sur (latitud)')],
                ['north', tr('North (latitude)', 'Norte (latitud)')],
              ].map(([key, name]) => (
                <label key={key}>
                  {name}
                  <input
                    type="number"
                    step="any"
                    required
                    min={key === 'west' || key === 'east' ? -180 : -90}
                    max={key === 'west' || key === 'east' ? 180 : 90}
                    value={bounds[key as keyof typeof bounds]}
                    onChange={(e) =>
                      setBounds((b) => ({
                        ...b,
                        [key]: e.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </div>
            <button className="button dark" type="submit">
              {tr('Apply coordinates', 'Aplicar coordenadas')}
              <ArrowRight size={16} />
            </button>
          </form>
          <button className="text-link" onClick={onDraw}>
            {tr('Draw on the map', 'Dibujar sobre el mapa')}
            <ArrowUpRight size={15} />
          </button>
          <p className="small-note">
            {tr(
              'For areas that cross the antimeridian, pick a country with multipolygon geometry or split the selection.',
              'Para áreas que cruzan el antimeridiano, selecciona un país con geometría multipolígono o divide la selección.',
            )}
          </p>
        </div>
      ) : modal === 'export' ? (
        <div className="dialog-body">
          <p>
            {MONTHS[selection.selected_month - 1]} {selection.selected_year} ·{' '}
            {analysis?.metric_label}
          </p>
          {!puedeExportar ? (
            <div className="permission-state" role="alert">
              <ShieldAlert size={17} />
              <div>
                <strong>
                  {tr(
                    'Downloads need a signed-in account.',
                    'Las descargas requieren una cuenta con sesión.',
                  )}
                </strong>
                <p>
                  {user
                    ? tr(
                        'Your role can only view. Ask for an analyst or administrator account to export this analysis.',
                        'Tu rol solo consulta. Pide una cuenta de analista o administrador para exportar este análisis.',
                      )
                    : tr(
                        'Sign in with an analyst or admin account to download the calendar, the observations and the evidence file.',
                        'Entra con una cuenta de analista o admin para descargar el calendario, las observaciones y el expediente.',
                      )}
                </p>
                <button className="button dark" onClick={onAccount}>
                  {tr('Sign in or create an account', 'Entrar o crear cuenta')}
                </button>
              </div>
            </div>
          ) : (
            <div className="export-list">
              {(harmonized
                ? [
                    [
                      'series',
                      tr('Harmonized monthly series', 'Serie mensual armonizada'),
                      tr(
                        'CSV · value, median, status, unit and FIRMS citation',
                        'CSV · valor, mediana, estado, unidad y cita FIRMS',
                      ),
                    ],
                    [
                      'package',
                      tr('Complete package', 'Paquete completo'),
                      tr(
                        'ZIP · series, every cell-day of the month, manifest and README',
                        'ZIP · serie, cada celda-día del mes, manifiesto y README',
                      ),
                    ],
                    [
                      'manifest',
                      tr('Evidence and provenance', 'Evidencia y procedencia'),
                      tr(
                        'JSON · selection, method version, limits and references',
                        'JSON · selección, versión del método, límites y referencias',
                      ),
                    ],
                  ]
                : [
                    [
                      'series',
                      tr('Monthly calendar', 'Calendario mensual'),
                      tr(
                        'CSV · values, median and archive status',
                        'CSV · valores, mediana y estado del archivo',
                      ),
                    ],
                    [
                      'detections',
                      tr('Original observations', 'Observaciones originales'),
                      tr(
                        'CSV · every row for the area and month',
                        'CSV · todas las filas del área y mes',
                      ),
                    ],
                    [
                      'manifest',
                      tr('Evidence and provenance', 'Evidencia y procedencia'),
                      tr(
                        'JSON · selection, revisions, hashes and limits',
                        'JSON · selección, revisiones, hashes y límites',
                      ),
                    ],
                    [
                      'report',
                      tr('Analysis report', 'Informe del análisis'),
                      tr(
                        'TXT · verified figures and sources',
                        'TXT · cifras verificadas y fuentes',
                      ),
                    ],
                  ]
              ).map(([id, title, detail]) => (
                <a key={id} href={`/api${analysisPath(harmonized)}/${analysis?.id}/exports/${id}`}>
                  <Download size={19} />
                  <span>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </span>
                  <ArrowUpRight size={16} />
                </a>
              ))}
              {analysis && (
                <a
                  href={
                    'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(seasonSVG(analysis))
                  }
                  download={'NINA_' + analysis.id + tr('_season.svg', '_temporada.svg')}
                >
                  <Download size={19} />
                  <span>
                    <strong>{tr('Season profile', 'Perfil de temporada')}</strong>
                    <small>
                      {tr(
                        'SVG · series, median and analysis context',
                        'SVG · serie, mediana y contexto del análisis',
                      )}
                    </small>
                  </span>
                  <ArrowUpRight size={16} />
                </a>
              )}
            </div>
          )}
          <button className="button outline" onClick={onShare}>
            <Share2 size={16} />
            {tr('Copy the investigation link', 'Copiar enlace de la investigación')}
          </button>
        </div>
      ) : modal === 'explain' ? (
        <div className="dialog-body explanation">
          <div className="assistant-context">
            <span>
              <Sparkles size={16} />
              {health?.llm_configured
                ? tr('AI with verified figures', 'IA con cifras verificadas')
                : tr('Evidence-based assistant', 'Asistente basado en evidencia')}
            </span>
            <label>
              {tr('Perspective', 'Perspectiva')}
              <select
                value={role}
                onChange={(e) => {
                  setRole(e.target.value)
                  setReply(null)
                }}
              >
                <option value="gestion">{tr('Land management', 'Gestión territorial')}</option>
                <option value="ciencia">{tr('Research', 'Investigación')}</option>
                <option value="comunicacion">{tr('Communication', 'Comunicación')}</option>
              </select>
            </label>
          </div>
          <p className="explanation-lead">
            {reply?.answer ||
              (selected?.value != null
                ? tr(
                    `${label}: ${fmt(selected.value)} archive detections in ${MONTHS[selection.selected_month - 1]} ${selection.selected_year}. ${selected.status === 'partial_archive' ? 'The period is partial; its monthly anomaly is omitted.' : 'Review its historical comparison and observation support.'}`,
                    `${label}: ${fmt(selected.value)} detecciones del archivo en ${MONTHS[selection.selected_month - 1].toLowerCase()} de ${selection.selected_year}. ${selected.status === 'partial_archive' ? 'El período es parcial; se omite su anomalía mensual.' : 'Revisa su comparación histórica y el soporte de observación.'}`,
                  )
                : tr(
                    'This period has no available output. You can check another source or add the archive.',
                    'El período no tiene una salida disponible. Puedes revisar otra fuente o incorporar el archivo.',
                  ))}
          </p>
          {reply?.framing && <p>{reply.framing}</p>}
          {reply?.guidance && <p className="role-guidance">{reply.guidance}</p>}
          <div className="question-list">
            {PRESETS.map(([en, es]) => (
              <button disabled={asking || !analysis} key={es} onClick={() => ask(es)}>
                {tr(en, es)}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
          <form
            className="question-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (question.trim()) ask(question)
            }}
          >
            <input
              aria-label={tr('Question about the selection', 'Pregunta sobre la selección')}
              value={question}
              maxLength={600}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={tr('Ask about this analysis…', 'Pregunta sobre este análisis…')}
            />
            <button
              className="button dark"
              disabled={asking || !analysis}
              aria-label={tr('Ask the analysis', 'Consultar análisis')}
            >
              <Send size={17} />
            </button>
          </form>
          {asking && (
            <p role="status">{tr('Querying the analysis…', 'Consultando el análisis…')}</p>
          )}
          {reply && (
            <div className="answer-evidence">
              <h3>{tr('Facts behind the answer', 'Hechos que sostienen la respuesta')}</h3>
              <dl>
                {reply.evidence.map((e) => (
                  <div key={e.id}>
                    <dt>{e.label}</dt>
                    <dd>
                      {e.value == null ? tr('Not available', 'No disponible') : String(e.value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          <button className="text-link" onClick={() => onModal('evidence')}>
            {tr('Open record and sources', 'Abrir expediente y fuentes')}
            <ArrowUpRight size={15} />
          </button>
          <p className="small-note">
            {health?.llm_configured
              ? tr(
                  'The language provider receives the summary; the figures stay under the server’s control.',
                  'El proveedor de lenguaje recibe el resumen; las cifras permanecen bajo control del servidor.',
                )
              : tr(
                  'The local engine reads verified results and templates. The machine learning model lives in the lab.',
                  'El motor local consulta resultados y plantillas verificadas. El modelo de aprendizaje automático está en el laboratorio.',
                )}
          </p>
        </div>
      ) : (
        <div className="dialog-body evidence-body">
          <p>
            {MONTHS[selection.selected_month - 1]} {selection.selected_year} ·{' '}
            {sourceName(selection.source, selection.platform)}
          </p>
          <dl>
            <div>
              <dt>{tr('Identifier', 'Identificador')}</dt>
              <dd>{analysis?.id}</dd>
            </div>
            <div>
              <dt>{tr('Data revision', 'Revisión de datos')}</dt>
              <dd>{analysis?.data_revision}</dd>
            </div>
            <div>
              <dt>{tr('Status', 'Estado')}</dt>
              <dd>
                {selected?.status === 'partial_archive'
                  ? tr('Partial archive', 'Archivo parcial')
                  : selected?.value == null
                    ? tr('No output available', 'Sin salida disponible')
                    : tr('Observed archive', 'Archivo observado')}
              </dd>
            </div>
            <div>
              <dt>{tr('Harmonization', 'Armonización')}</dt>
              <dd>
                {harmonized
                  ? tr(
                      `Experimental MODIS + VIIRS series, method ${analysis?.software_revision}; not scientifically validated`,
                      `Serie experimental MODIS + VIIRS, método ${analysis?.software_revision}; sin validación científica`,
                    )
                  : tr(
                      'Original observations; correction for observation opportunities pending',
                      'Observaciones originales; corrección por oportunidades pendiente',
                    )}
              </dd>
            </div>
            <div>
              <dt>{tr('Valid coverage', 'Cobertura válida')}</dt>
              <dd>{tr('Not reconstructed', 'No reconstruida')}</dd>
            </div>
          </dl>
          {analysis?.limitations.map((l) => (
            <p className="limitation" key={l}>
              {l}
            </p>
          ))}
          <h3>{tr('Windows covering this area', 'Ventanas que cubren esta área')}</h3>
          <ul className="window-list">
            {analysis?.archive_windows.slice(-12).map((w, i) => (
              <li key={i}>
                {w.start} → {w.end}
                <span>
                  {w.scope === 'world'
                    ? tr('Global', 'Mundial')
                    : w.scope === 'PER'
                      ? tr('Peru', 'Perú')
                      : tr('Query rectangle', 'Rectángulo de consulta')}
                </span>
              </li>
            ))}
          </ul>
          {analysis?.references.map((url, i) => (
            <a className="source-link" href={url} target="_blank" rel="noreferrer" key={url}>
              {i === 0
                ? tr('Source of the FIRMS records', 'Fuente de los registros FIRMS')
                : tr('Interpreting FIRMS detections', 'Interpretar las detecciones FIRMS')}
              <ArrowUpRight size={15} />
            </a>
          ))}
          <a
            className="button dark"
            href={`/api${analysisPath(harmonized)}/${analysis?.id}/exports/manifest`}
          >
            <FileJson size={16} />
            {tr('Download record', 'Descargar expediente')}
          </a>
        </div>
      )}
    </dialog>
  )
}
