import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Map as MapIcon,
  Send,
  ShieldAlert,
  Sparkles,
  Table2,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import AnalystVisualView from './AnalystVisual'
import { analystStatus, askAnalystStream, reportDocumentUrl, reportPackageUrl } from './api'
import { getLang, tr } from './i18n'
import type {
  AnalystAction,
  AnalystAnswer,
  AnalystEvent,
  AnalystStatus,
  AnalystTurn,
  ReportRequest,
} from './types'

// What the user sees while NINA works: one line per real step, in the order they happen.
const STEP_TEXT: Record<string, [string, string]> = {
  territory_profile: ['Reading the territorial profile', 'Leyendo el perfil territorial'],
  activity_series: ['Reading the monthly series', 'Leyendo la serie mensual'],
  compare_departments: ['Comparing departments', 'Comparando departamentos'],
  validation_summary: ['Reading the validation results', 'Leyendo los resultados de validación'],
  method_notes: ['Reading the method notes', 'Leyendo las notas de método'],
  find_territory: ['Finding the place', 'Buscando el lugar'],
  calculate: ['Calculating', 'Calculando'],
  show_visual: ['Drawing a chart from NINA data', 'Dibujando un gráfico con datos de NINA'],
  propose_action: ['Preparing a button', 'Preparando un botón'],
  web_search: ['Searching official sources', 'Buscando en fuentes oficiales'],
}
type Step = { key: string; text: string; done: boolean }
function nextSteps(steps: Step[], event: AnalystEvent): Step[] {
  const close = (list: Step[]) => list.map((s) => ({ ...s, done: true }))
  if (event.type === 'tool') {
    const text = STEP_TEXT[event.name] ? tr(...STEP_TEXT[event.name]) : event.name
    if (event.state === 'start') return [...close(steps), { key: `${event.name}-${steps.length}`, text, done: false }]
    const open = [...steps].reverse().find((s) => !s.done && s.key.startsWith(event.name))
    if (open) return steps.map((s) => (s === open ? { ...s, done: true } : s))
    return [...close(steps), { key: `${event.name}-${steps.length}`, text, done: true }]
  }
  if (event.type === 'thinking')
    return [
      ...close(steps),
      {
        key: `thinking-${event.step}`,
        text: event.step === 1 ? tr('Planning the analysis', 'Planificando el análisis') : tr('Analysing the results', 'Analizando los resultados'),
        done: false,
      },
    ]
  if (event.type === 'verifying')
    return [...close(steps), { key: 'verify', text: tr('Checking every figure against NINA data', 'Contrastando cada cifra con los datos de NINA'), done: false }]
  if (event.type === 'fallback')
    return [
      ...close(steps),
      { key: 'fallback', text: tr('Preparing the verified deterministic answer', 'Preparando la respuesta determinista verificada'), done: false },
    ]
  return steps
}

// Questions a specialist would ask first; the text sent follows the interface language.
const PRESETS: [string, string][] = [
  ['What does this period show?', '¿Qué muestra este período?'],
  ['Is the trend real or a sensor artefact?', '¿La tendencia es real o un artefacto del sensor?'],
  ['Which departments stand out this month?', '¿Qué departamentos destacan este mes?'],
  [
    'How do detected fire events compare with INDECI emergencies?',
    '¿Cómo se comparan los eventos detectados con las emergencias de INDECI?',
  ],
  ['How reliable is the harmonization here?', '¿Qué tan fiable es la armonización aquí?'],
  ['What can NINA not answer?', '¿Qué no puede responder NINA?'],
]

const TOOL_NAMES: Record<string, [string, string]> = {
  territory_profile: ['territorial profile', 'perfil territorial'],
  activity_series: ['monthly series', 'serie mensual'],
  compare_departments: ['department comparison', 'comparación de departamentos'],
  validation_summary: ['validation results', 'resultados de validación'],
  method_notes: ['method notes', 'notas de método'],
  find_territory: ['place search', 'búsqueda de lugares'],
  calculate: ['checked calculation', 'cálculo verificado'],
  show_visual: ['chart or table', 'gráfico o tabla'],
  propose_action: ['interface action', 'acción en la interfaz'],
  web_search: ['official web sources', 'fuentes oficiales en la web'],
}

const ACTION_ICONS = {
  show_on_map: MapIcon,
  open_calendar: CalendarDays,
  open_priorities: Table2,
  open_report: FileText,
  download_data: Download,
}

/** A button the user presses: navigation goes through the app; reports and packages are plain links. */
function ActionButton({ action, onAction }: { action: AnalystAction; onAction?: (a: AnalystAction) => void }) {
  const Icon = ACTION_ICONS[action.kind]
  if (action.kind === 'open_report' || action.kind === 'download_data') {
    if (!action.report_id) return null
    const href =
      action.kind === 'open_report' ? reportDocumentUrl(action.report_id) : reportPackageUrl(action.report_id)
    return (
      <a className="button outline" href={href} target="_blank" rel="noreferrer">
        <Icon size={15} />
        {action.label}
      </a>
    )
  }
  if (!onAction) return null
  return (
    <button className="button outline" onClick={() => onAction(action)}>
      <Icon size={15} />
      {action.label}
    </button>
  )
}

const LIST_ITEM = /^(?:[-•*]|\d+\.)\s+/

/** Paragraphs separated by blank lines; lines starting with "- " or "1. " become a list. */
function AnswerText({ text }: { text: string }) {
  const clean = text.replace(/\*\*(.+?)\*\*/g, '$1')
  return (
    <div className="analyst-answer">
      {clean.split(/\n{2,}/).map((block, index) => {
        const lines = block.split('\n').filter((line) => line.trim())
        const items = lines.filter((line) => LIST_ITEM.test(line))
        const head = lines.filter((line) => !LIST_ITEM.test(line)).join(' ')
        return (
          <div key={index}>
            {head && <p>{head}</p>}
            {items.length > 0 && (
              <ul>
                {items.map((line, i) => (
                  <li key={i}>{line.replace(LIST_ITEM, '')}</li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}

/**
 * Analytical assistant for the harmonized record. It answers about the territory and month on
 * screen with NINA's own tools; every figure shown has been checked against the tool results.
 */
export default function AnalystPanel({
  context,
  onError,
  onEvidence,
  onAction,
}: {
  context: ReportRequest | null
  onError: (message: string) => void
  onEvidence?: () => void
  onAction?: (action: AnalystAction) => void
}) {
  const [status, setStatus] = useState<AnalystStatus | null>(null),
    [reply, setReply] = useState<AnalystAnswer | null>(null),
    [history, setHistory] = useState<AnalystTurn[]>([]),
    [question, setQuestion] = useState(''),
    [asking, setAsking] = useState(false),
    [steps, setSteps] = useState<Step[]>([]),
    [pending, setPending] = useState('')
  const key = JSON.stringify(context)
  const current = useRef(key)
  current.current = key

  useEffect(() => {
    analystStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])
  useEffect(() => {
    setReply(null)
    setHistory([])
  }, [key])

  async function ask(text: string) {
    if (!context || asking) return
    setAsking(true)
    setSteps([])
    setPending(text)
    const sent = key
    try {
      const answer = await askAnalystStream(
        { question: text, language: getLang(), context, history },
        (event) => {
          if (current.current === sent) setSteps((previous) => nextSteps(previous, event))
        },
      )
      if (current.current !== sent) return
      setReply(answer)
      setHistory((previous) =>
        [
          ...previous,
          { role: 'user' as const, content: text },
          { role: 'assistant' as const, content: answer.answer },
        ].slice(-6),
      )
      setQuestion('')
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error))
    } finally {
      setAsking(false)
      setPending('')
    }
  }

  const ai = status?.engine === 'claude'
  const verification = reply?.verification
  return (
    <>
      <div className="assistant-context">
        <span>
          <Sparkles size={16} />
          {ai
            ? tr('AI analyst · every figure checked against NINA data', 'Analista IA · cada cifra contrastada con los datos de NINA')
            : tr('Analyst · every figure taken from NINA data', 'Analista · cada cifra tomada de los datos de NINA')}
        </span>
      </div>
      {reply ? (
        <AnswerText text={reply.answer} />
      ) : (
        <p className="explanation-lead">
          {context
            ? tr(
                'Ask about the territory and month on screen: how unusual it is, whether the trend is real, how detected fires compare with INDECI emergencies, forest loss, climate context or how reliable the harmonization is.',
                'Pregunta sobre el territorio y el mes en pantalla: qué tan inusual es, si la tendencia es real, cómo se comparan los incendios detectados con las emergencias de INDECI, la pérdida forestal, el contexto climático o qué tan fiable es la armonización.',
              )
            : tr(
                'Select a country, a Peruvian region or a drawn area to ask about it. The planet as a whole has no territorial profile.',
                'Selecciona un país, una región del Perú o un área dibujada para consultar. El planeta completo no tiene perfil territorial.',
              )}
        </p>
      )}
      {reply && reply.visuals.length > 0 && (
        <div className="analyst-visuals">
          {reply.visuals.map((visual) => (
            <AnalystVisualView key={visual.id} visual={visual} />
          ))}
        </div>
      )}
      {reply && reply.sources.length > 0 && (
        <div className="analyst-sources">
          <h3>{tr('Official sources cited', 'Fuentes oficiales citadas')}</h3>
          <ol>
            {reply.sources.map((source) => (
              <li key={source.url + source.cited_text}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
                {source.cited_text && <q>{source.cited_text}</q>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {reply && reply.actions.length > 0 && (
        <div className="analyst-actions">
          {reply.actions.map((action) => (
            <ActionButton key={action.id} action={action} onAction={onAction} />
          ))}
        </div>
      )}
      {reply?.notice && (
        <p className="analyst-notice">
          <ShieldAlert size={14} />
          {reply.notice}
        </p>
      )}
      {reply && verification && (
        <p className={`analyst-check ${verification.passed ? 'ok' : 'warn'}`}>
          {verification.passed ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
          {reply.abstained
            ? tr('Outside what NINA can answer: no data were used.', 'Fuera de lo que NINA puede responder: no se usaron datos.')
            : verification.passed
              ? tr(
                  `${verification.checked} figures checked against NINA data`,
                  `${verification.checked} cifras contrastadas con los datos de NINA`,
                )
              : tr(
                  `Figures without a source: ${verification.unverified.join(', ')}`,
                  `Cifras sin fuente: ${verification.unverified.join(', ')}`,
                )}
        </p>
      )}
      {reply && reply.follow_ups.length > 0 && (
        <h3 className="analyst-next">{tr('Ask next', 'Siguiente pregunta')}</h3>
      )}
      <div className="question-list">
        {(reply && reply.follow_ups.length > 0
          ? reply.follow_ups
          : PRESETS.map(([en, es]) => tr(en, es))
        ).map((text) => (
          <button disabled={asking || !context} key={text} onClick={() => ask(text)}>
            {text}
            <ArrowUpRight size={14} />
          </button>
        ))}
      </div>
      <form
        className="question-form"
        onSubmit={(event) => {
          event.preventDefault()
          if (question.trim()) ask(question.trim())
        }}
      >
        <input
          aria-label={tr('Question about the selection', 'Pregunta sobre la selección')}
          value={question}
          maxLength={600}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={tr('Ask a technical question…', 'Haz una pregunta técnica…')}
        />
        <button className="button dark" disabled={asking || !context} aria-label={tr('Ask', 'Consultar')}>
          <Send size={17} />
        </button>
      </form>
      {asking && (
        <div className="analyst-progress" role="status" aria-live="polite">
          <p className="analyst-question">“{pending}”</p>
          <ol>
            {(steps.length ? steps : [{ key: 'start', text: tr('Starting', 'Iniciando'), done: false }]).map((step) => (
              <li key={step.key} className={step.done ? 'done' : 'active'}>
                {step.done ? <CheckCircle2 size={14} /> : <Loader2 size={14} className="spin" />}
                {step.text}
              </li>
            ))}
          </ol>
        </div>
      )}
      {reply && reply.facts.length > 0 && (
        <div className="answer-evidence">
          <h3>{tr('Facts behind the answer', 'Hechos que sostienen la respuesta')}</h3>
          <dl>
            {reply.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {reply && reply.tools.length > 0 && (
        <p className="analyst-tools">
          {tr('Consulted', 'Consultado')}:{' '}
          {[...new Set(reply.tools.map((tool) => tool.name))]
            .map((name) => (TOOL_NAMES[name] ? tr(...TOOL_NAMES[name]) : name))
            .join(' · ')}
        </p>
      )}
      <div className="analyst-links">
        {reply?.report_id && (
          <a className="text-link" href={reportDocumentUrl(reply.report_id)} target="_blank" rel="noreferrer">
            <FileText size={14} />
            {tr('Open the technical report', 'Abrir el informe técnico')}
          </a>
        )}
        {onEvidence && (
          <button className="text-link" onClick={onEvidence}>
            {tr('Open record and sources', 'Abrir expediente y fuentes')}
            <ArrowUpRight size={15} />
          </button>
        )}
      </div>
      <p className="small-note">
        {ai
          ? tr(
              'The question and the tool results are sent to the language provider (Anthropic). An answer is shown only if every figure in it appears in NINA’s data; otherwise the deterministic answer is used.',
              'La pregunta y los resultados de las herramientas se envían al proveedor de lenguaje (Anthropic). Una respuesta solo se muestra si cada cifra aparece en los datos de NINA; si no, se usa la respuesta determinista.',
            )
          : tr(
              'Answers are built from NINA’s tools and templates, and each figure is checked against the tool results. NINA does not forecast fires, attribute causes or give operational instructions.',
              'Las respuestas se construyen con las herramientas y plantillas de NINA, y cada cifra se contrasta con los resultados. NINA no pronostica incendios, no atribuye causas ni da instrucciones operativas.',
            )}
      </p>
    </>
  )
}
