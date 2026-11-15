import { FileText, Loader2 } from 'lucide-react'
import { useState } from 'react'

import { createReport, reportDocumentUrl } from './api'
import { tr } from './i18n'
import type { ReportRequest } from './types'

/**
 * Opens the territorial evidence report in a new tab. The tab is opened on the click itself (so
 * pop-up blockers allow it) and receives the document once the server has built the report.
 */
export default function ReportButton({
  body,
  className = '',
  onError,
}: {
  body: ReportRequest | null
  className?: string
  onError?: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  async function open() {
    if (!body || busy) return
    const tab = window.open('', '_blank')
    if (tab) {
      tab.document.title = 'NINA'
      // A waiting page with a moving indicator: building a report takes a few seconds.
      tab.document.body.innerHTML = `<style>@keyframes s{to{transform:rotate(360deg)}}</style>
        <div style="font:16px system-ui;margin:15vh auto;max-width:520px;color:#203a3c;text-align:center">
        <div style="width:38px;height:38px;margin:0 auto 18px;border:4px solid #e9bc78;border-top-color:#c2410c;
        border-radius:50%;animation:s .9s linear infinite"></div>
        <p style="font-weight:600">${tr('Preparing the technical report…', 'Preparando el informe técnico…')}</p>
        <p style="color:#697873;font-size:14px">${tr(
          'NINA is computing the record, events, forest, climate and satellite images of this territory. It takes a few seconds.',
          'NINA está calculando el registro, los eventos, el bosque, el clima y las imágenes satelitales de este territorio. Toma unos segundos.',
        )}</p></div>`
    }
    setBusy(true)
    try {
      const report = await createReport(body)
      const url = reportDocumentUrl(report.id)
      if (tab) tab.location.href = url
      else window.location.href = url
    } catch (error) {
      tab?.close()
      onError?.(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }
  return (
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
  )
}
