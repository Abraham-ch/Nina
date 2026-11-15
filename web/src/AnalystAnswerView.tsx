import { CalendarDays, CheckCircle2, Download, FileText, Map as MapIcon, ShieldAlert, Table2 } from 'lucide-react'

import AnalystVisualView from './AnalystVisual'
import { reportDocumentUrl, reportPackageUrl } from './api'
import { tr } from './i18n'
import type { AnalystAction, AnalystAnswer } from './types'

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

/** One answer of the conversation: text, charts and tables, buttons, sources and how it was checked. */
export default function AnalystAnswerView({
  answer,
  onAction,
}: {
  answer: AnalystAnswer
  onAction?: (action: AnalystAction) => void
}) {
  const verification = answer.verification
  return (
    <div className="analyst-reply">
      <AnswerText text={answer.answer} />
      {answer.visuals.length > 0 && (
        <div className="analyst-visuals">
          {answer.visuals.map((visual) => (
            <AnalystVisualView key={visual.id} visual={visual} />
          ))}
        </div>
      )}
      {answer.sources.length > 0 && (
        <div className="analyst-sources">
          <h3>{tr('Official sources cited', 'Fuentes oficiales citadas')}</h3>
          <ol>
            {answer.sources.map((source) => (
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
      {answer.actions.length > 0 && (
        <div className="analyst-actions">
          {answer.actions.map((action) => (
            <ActionButton key={action.id} action={action} onAction={onAction} />
          ))}
        </div>
      )}
      {answer.notice && (
        <p className="analyst-notice">
          <ShieldAlert size={14} />
          {answer.notice}
        </p>
      )}
      <p className={`analyst-check ${verification.passed ? 'ok' : 'warn'}`}>
        {verification.passed ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
        {answer.abstained
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
      {(answer.facts.length > 0 || answer.tools.length > 0) && (
        <details className="answer-evidence">
          <summary>{tr('Facts and sources behind the answer', 'Hechos y fuentes de la respuesta')}</summary>
          {answer.facts.length > 0 && (
            <dl>
              {answer.facts.map((fact) => (
                <div key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {answer.tools.length > 0 && (
            <p className="analyst-tools">
              {tr('Consulted', 'Consultado')}:{' '}
              {[...new Set(answer.tools.map((tool) => tool.name))]
                .map((name) => (TOOL_NAMES[name] ? tr(...TOOL_NAMES[name]) : name))
                .join(' · ')}
            </p>
          )}
          {answer.report_id && (
            <a className="text-link" href={reportDocumentUrl(answer.report_id)} target="_blank" rel="noreferrer">
              <FileText size={14} />
              {tr('Open the technical report', 'Abrir el informe técnico')}
            </a>
          )}
        </details>
      )}
    </div>
  )
}
