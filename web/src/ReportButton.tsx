import { ExternalLink, FileText, Loader2, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { createReport, reportDocumentUrl } from './api'
import { tr } from './i18n'
import type { ReportRequest } from './types'

/** Builds the territorial evidence report and shows it in a modal (the document keeps its own print and download bar). */
export default function ReportButton({
  body,
  className = '',
  onError,
}: {
  body: ReportRequest | null
  className?: string
  onError?: (message: string) => void
}) {
  const [busy, setBusy] = useState(false),
    [url, setUrl] = useState(''),
    dialog = useRef<HTMLDialogElement>(null)
  async function open() {
    if (!body || busy) return
    setUrl('')
    setBusy(true)
    dialog.current?.showModal()
    try {
      setUrl(reportDocumentUrl((await createReport(body)).id))
    } catch (error) {
      dialog.current?.close()
      onError?.(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button
        className={className}
        onClick={open}
        disabled={!body || busy}
        title={tr(
          'Printable technical report of this territory and month',
          'Informe técnico imprimible de este territorio y mes',
        )}
      >
        {busy ? <Loader2 size={15} className="spin" /> : <FileText size={15} />}
        {busy ? tr('Preparing…', 'Preparando…') : tr('Technical report', 'Informe técnico')}
      </button>
      <dialog ref={dialog} className="nina-dialog report-dialog" onClose={() => setUrl('')}>
        <div className="dialog-head">
          <h2>{tr('Technical report', 'Informe técnico')}</h2>
          {url && (
            <a className="text-link" href={url} target="_blank" rel="noreferrer">
              <ExternalLink size={15} />
              {tr('Open in a new tab', 'Abrir en una pestaña nueva')}
            </a>
          )}
          <button onClick={() => dialog.current?.close()} aria-label={tr('Close', 'Cerrar')}>
            <X size={18} />
          </button>
        </div>
        {url ? (
          <iframe src={url} title={tr('Technical report', 'Informe técnico')} />
        ) : (
          <div className="report-wait" role="status">
            <Loader2 size={34} className="spin" />
            <strong>
              {tr('Preparing the technical report…', 'Preparando el informe técnico…')}
            </strong>
            <p>
              {tr(
                'NINA is computing the record, events, forest, climate and satellite images of this territory. It takes a few seconds.',
                'NINA está calculando el registro, los eventos, el bosque, el clima y las imágenes satelitales de este territorio. Toma unos segundos.',
              )}
            </p>
          </div>
        )}
      </dialog>
    </>
  )
}
