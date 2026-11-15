import { ArrowUpRight, CheckCircle2, Loader2, RotateCcw, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import AnalystAnswerView from './AnalystAnswerView'
import { analystStatus, askAnalystStream, months } from './api'
import { getLang, tr } from './i18n'
import type { AnalystAction, AnalystAnswer, AnalystEvent, AnalystStatus, ReportRequest } from './types'

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
  if (event.type === 'thinking') {
    const text =
      event.step === 1
        ? tr('Planning the analysis', 'Planificando el análisis')
        : tr('Analysing the results', 'Analizando los resultados')
    return [...close(steps), { key: `thinking-${event.step}`, text, done: false }]
  }
  if (event.type === 'verifying') {
    const text = tr('Checking every figure against NINA data', 'Contrastando cada cifra con los datos de NINA')
    return [...close(steps), { key: 'verify', text, done: false }]
  }
  if (event.type === 'fallback') {
    const text = tr('Preparing the verified deterministic answer', 'Preparando la respuesta determinista verificada')
    return [...close(steps), { key: 'fallback', text, done: false }]
  }
  return steps
}

// Questions a specialist would ask first; the text sent follows the interface language.
const PRESETS: [string, string][] = [
  ['What does this period show?', '¿Qué muestra este período?'],
  ['Is the trend real or a sensor artefact?', '¿La tendencia es real o un artefacto del sensor?'],
  ['How do detected fires compare with official records?', '¿Cómo se comparan los incendios detectados con los registros oficiales?'],
  ['How reliable is the harmonization here?', '¿Qué tan fiable es la armonización aquí?'],
  ['What can NINA not answer?', '¿Qué no puede responder NINA?'],
]

type Turn = { id: string; question: string; where: string; answer?: AnalystAnswer; error?: string }
const STORE = 'nina.analyst.thread'

function loadThread(): Turn[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE) || '[]')
    return Array.isArray(saved) ? saved.filter((t: Turn) => t.answer || t.error) : []
  } catch {
    return []
  }
}
function saveThread(thread: Turn[]) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(thread.filter((t) => t.answer || t.error).slice(-20)))
  } catch {
    /* storage unavailable (private mode, quota): the conversation simply is not kept across reloads */
  }
}

/** Where a question was asked: the territory and month on screen. */
function where(context: ReportRequest): string {
  const place = context.place_name || (context.country === 'world' ? tr('Drawn area', 'Área dibujada') : context.country)
  return `${place} · ${months()[context.month - 1]} ${context.year}`
}

/**
 * Conversation with NINA's analyst about the territory and month on screen. The conversation is kept when the
 * panel is closed (and across reloads of the tab); every figure of every answer is checked against NINA's data.
 */
export default function AnalystPanel({
  context,
  onError,
  onAction,
}: {
  context: ReportRequest | null
  onError: (message: string) => void
  onAction?: (action: AnalystAction) => void
}) {
  const [status, setStatus] = useState<AnalystStatus | null>(null),
    [thread, setThread] = useState<Turn[]>(loadThread),
    [question, setQuestion] = useState(''),
    [steps, setSteps] = useState<Step[]>([])
  const asking = thread.some((t) => !t.answer && !t.error)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    analystStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])
  useEffect(() => saveThread(thread), [thread])
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [thread.length, steps.length, asking])

  async function ask(text: string) {
    if (!context || asking || !text.trim()) return
    const id = `${Date.now()}`
    const history = thread
      .filter((t) => t.answer)
      .slice(-3)
      .flatMap((t) => [
        { role: 'user' as const, content: t.question },
        { role: 'assistant' as const, content: t.answer!.answer.slice(0, 3900) },
      ])
    setQuestion('')
    setSteps([])
    setThread((previous) => [...previous, { id, question: text.trim(), where: where(context) }])
    try {
      const answer = await askAnalystStream(
        { question: text.trim(), language: getLang(), context, history },
        (event) => setSteps((previous) => nextSteps(previous, event)),
      )
      setThread((previous) => previous.map((t) => (t.id === id ? { ...t, answer } : t)))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setThread((previous) => previous.map((t) => (t.id === id ? { ...t, error: message } : t)))
      onError(message)
    }
  }

  const last = [...thread].reverse().find((t) => t.answer)
  const suggestions = last?.answer?.follow_ups.length
    ? last.answer.follow_ups
    : PRESETS.map(([en, es]) => tr(en, es))
  const ai = status?.engine === 'claude'
  return (
    <div className="analyst-chat">
      <div className="analyst-thread">
        {thread.length === 0 && (
          <p className="explanation-lead">
            {context
              ? tr(
                  'Ask about the territory and month on screen. NINA answers with its own data, draws charts, can move the map for you and checks every figure.',
                  'Pregunta sobre el territorio y el mes en pantalla. NINA responde con sus propios datos, dibuja gráficos, puede mover el mapa por ti y verifica cada cifra.',
                )
              : tr(
                  'Select a country, a Peruvian region or a drawn area to ask about it. The planet as a whole has no territorial profile.',
                  'Selecciona un país, una región del Perú o un área dibujada para consultar. El planeta completo no tiene perfil territorial.',
                )}
          </p>
        )}
        {thread.map((turn) => (
          <article key={turn.id} className="analyst-turn">
            <div className="analyst-user">
              <span>{turn.where}</span>
              <p>{turn.question}</p>
            </div>
            {turn.answer ? (
              <AnalystAnswerView answer={turn.answer} onAction={onAction} />
            ) : turn.error ? (
              <p className="analyst-notice">{turn.error}</p>
            ) : (
              <ol className="analyst-progress" role="status" aria-live="polite">
                {(steps.length ? steps : [{ key: 'start', text: tr('Starting', 'Iniciando'), done: false }]).map(
                  (step) => (
                    <li key={step.key} className={step.done ? 'done' : 'active'}>
                      {step.done ? <CheckCircle2 size={14} /> : <Loader2 size={14} className="spin" />}
                      {step.text}
                    </li>
                  ),
                )}
              </ol>
            )}
          </article>
        ))}
        {!asking && context && (
          <div className="question-list">
            {suggestions.map((text) => (
              <button key={text} onClick={() => ask(text)}>
                {text}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>
      <form
        className="question-form"
        onSubmit={(event) => {
          event.preventDefault()
          ask(question)
        }}
      >
        <input
          aria-label={tr('Question about the selection', 'Pregunta sobre la selección')}
          value={question}
          maxLength={600}
          disabled={!context}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={asking ? tr('NINA is working…', 'NINA está trabajando…') : tr('Ask a question…', 'Haz una pregunta…')}
        />
        <button className="button dark" disabled={asking || !context || !question.trim()} aria-label={tr('Ask', 'Consultar')}>
          {asking ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
        </button>
      </form>
      <div className="analyst-footer">
        <small>
          {ai
            ? tr('Claude via Anthropic · figures checked against NINA data', 'Claude vía Anthropic · cifras contrastadas con los datos de NINA')
            : tr('Deterministic analyst · figures from NINA data', 'Analista determinista · cifras de los datos de NINA')}
        </small>
        {thread.length > 0 && !asking && (
          <button className="text-link" onClick={() => setThread([])}>
            <RotateCcw size={13} />
            {tr('New conversation', 'Nueva conversación')}
          </button>
        )}
      </div>
    </div>
  )
}
