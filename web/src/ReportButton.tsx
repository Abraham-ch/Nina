import { FileText } from 'lucide-react'
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
      tab.document.body.innerHTML = `<p style="font:16px system-ui;margin:40px;color:#203a3c">${tr(
        'Preparing the technical report…',
        'Preparando el informe técnico…',
      )}</p>`
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
      <FileText size={15} />
      {busy ? tr('Preparing…', 'Preparando…') : tr('Technical report', 'Informe técnico')}
    </button>
  )
}
