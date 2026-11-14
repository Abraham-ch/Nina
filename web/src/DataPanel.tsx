import { ArrowUpRight, CloudDownload, Upload, RefreshCw, CheckCircle2, Clock3 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { api, post, fmt, bytes } from './api'
import { tr, locale } from './i18n'
import type { Analysis, Catalog, Health, Job, Selection, Status, User } from './types'
type Props = {
  status: Status | null
  catalog: Catalog | null
  health: Health | null
  jobs: Job[]
  selection: Selection
  analysis: Analysis | null
  user: User | null
  onRefresh: () => void
  onNotice: (text: string) => void
  onError: (text: string) => void
}
export default function DataPanel({
  status,
  catalog,
  health,
  jobs,
  selection,
  analysis,
  user,
  onRefresh,
  onNotice,
  onError,
}: Props) {
  const [product, setProduct] = useState(''),
    [scope, setScope] = useState<'world' | 'PER' | 'custom'>(selection.scope),
    [source, setSource] = useState('modis'),
    [busy, setBusy] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  useEffect(() => setScope(selection.scope), [selection.scope, selection.area_label])
  const date = `${selection.selected_year}-${String(selection.selected_month).padStart(2, '0')}`
  const eligible =
    catalog?.products.filter((p) => p.start.slice(0, 7) <= date && p.end.slice(0, 7) >= date) || []
  const preferred =
    eligible.find((p) => p.source === selection.source && p.product.endsWith('_SP')) ||
    eligible.find((p) => p.source === selection.source) ||
    eligible[0]
  const chosen = eligible.some((p) => p.product === product) ? product : preferred?.product || ''
  const active = jobs.some((j) => ['queued', 'running'].includes(j.status))
  const puedeAdministrar = !!user && user.role === 'admin'
  const worldFiles = status?.batches.filter((b) => b.spatial_scope === 'world') || []
  const worldStart = worldFiles
    .map((b) => b.coverage_start)
    .filter(Boolean)
    .sort()[0]
  const worldEnd = worldFiles
    .map((b) => b.coverage_end)
    .filter(Boolean)
    .sort()
    .at(-1)
  async function acquireMonth() {
    setBusy(true)
    try {
      await post('/acquisitions/month', {
        product: chosen,
        year: selection.selected_year,
        month: selection.selected_month,
        scope,
        geometry: scope === 'custom' ? selection.geometry : null,
      })
      onNotice(
        tr(
          'Monthly download started. Keep exploring; the calendar will update with the new data.',
          'Descarga del mes iniciada. Puedes seguir explorando; el calendario se actualizará con los datos incorporados.',
        ),
      )
      onRefresh()
    } catch (e) {
      onError(String(e))
    } finally {
      setBusy(false)
    }
  }
  async function recent() {
    setBusy(true)
    try {
      await post('/acquisitions', { scope: 'world', days: 1 })
      onNotice(
        tr(
          'Global update queued. The available date will be checked for the three products.',
          'Actualización mundial en cola. Se verificará la fecha disponible para los tres productos.',
        ),
      )
      onRefresh()
    } catch (e) {
      onError(String(e))
    } finally {
      setBusy(false)
    }
  }
  async function upload() {
    const selected = file.current?.files?.[0]
    if (!selected) return
    setBusy(true)
    try {
      const form = new FormData()
      form.set('file', selected)
      form.set('source', source)
      form.set('spatial_scope', scope)
      if (scope === 'custom' && selection.geometry)
        form.set('spatial_geometry', JSON.stringify(selection.geometry))
      await api('/import', { method: 'POST', body: form })
      onNotice(
        tr(
          'File queued for import. Its time coverage will be kept as unknown.',
          'Archivo en cola de importación. Su cobertura temporal se conservará como desconocida.',
        ),
      )
      onRefresh()
    } catch (e) {
      onError(String(e))
    } finally {
      setBusy(false)
    }
  }
  const jobStatus: Record<string, string> = {
    complete: tr('Completed', 'Completado'),
    failed: tr('Failed', 'Falló'),
    running: tr('Processing', 'Procesando'),
    queued: tr('Queued', 'En cola'),
    interrupted: tr('Interrupted', 'Interrumpido'),
  }
  return (
    <section className="data-page">
      <div className="section-title">
        <div>
          <span className="kicker">{tr('Open the evidence', 'Abrir la evidencia')}</span>
          <h1>{tr('An archive you can review.', 'Un archivo que puedes revisar.')}</h1>
          <p>
            {tr(
              'Sources, periods, completeness and acquisition jobs.',
              'Fuentes, períodos, integridad y trabajos de adquisición.',
            )}
          </p>
        </div>
        <button className="button outline" onClick={onRefresh}>
          <RefreshCw size={16} />
          {tr('Refresh', 'Actualizar')}
        </button>
      </div>
      <div className="data-summary">
        <div>
          <strong>{fmt(status?.observations)}</strong>
          <span>{tr('Normalized observations', 'Observaciones normalizadas')}</span>
        </div>
        <div>
          <strong>{status?.batches.length || 0}</strong>
          <span>{tr('Files with provenance', 'Archivos con procedencia')}</span>
        </div>
        <div>
          <strong>{status?.last_date?.slice(0, 10) || '—'}</strong>
          <span>{tr('Latest detection added', 'Última detección incorporada')}</span>
        </div>
        <div>
          <strong>{status ? bytes(status.database_bytes) : '—'}</strong>
          <span>{tr('Local analytical database', 'Base analítica local')}</span>
        </div>
      </div>
      <div className="acquisition-layout">
        <section className="acquisition">
          <span className="kicker">
            {tr('Extend your investigation', 'Ampliar tu investigación')}
          </span>
          <h2>{tr('Add a FIRMS month.', 'Incorporar un mes de FIRMS.')}</h2>
          <p>
            {analysis?.area_name || tr('Your selection', 'Tu selección')} · {date}.{' '}
            {tr(
              'It downloads in windows of up to five days and every file keeps its hash and scope.',
              'Se descarga en ventanas de hasta cinco días y cada archivo conserva su hash y ámbito.',
            )}
          </p>
          <div className="acquisition-form">
            <label>
              {tr('Territory', 'Territorio')}
              <select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}>
                <option value="world">{tr('The whole planet', 'Todo el planeta')}</option>
                <option value="PER">{tr('Peru', 'Perú')}</option>
                {selection.geometry && (
                  <option value="custom">
                    {tr('Selected area', 'Área seleccionada')} · {analysis?.area_name}
                  </option>
                )}
              </select>
            </label>
            <label>
              {tr('Available product', 'Producto disponible')}
              <select value={chosen} onChange={(e) => setProduct(e.target.value)}>
                {eligible.map((p) => (
                  <option key={p.product} value={p.product}>
                    {p.product}
                  </option>
                ))}
                {!eligible.length && (
                  <option value="">
                    {tr(
                      'No verified product for this month',
                      'Sin producto verificado para este mes',
                    )}
                  </option>
                )}
              </select>
            </label>
          </div>
          {!puedeAdministrar && (
            <p className="permission-state" role="status">
              {tr(
                'Adding data, syncing FIRMS and training models requires an administrator account.',
                'Incorporar datos, sincronizar FIRMS y entrenar modelos pide una cuenta administradora.',
              )}{' '}
              {user
                ? tr('Your current role can only view.', 'Tu rol actual solo consulta.')
                : tr('You have not signed in yet.', 'Todavía no has iniciado sesión.')}
            </p>
          )}
          <button
            className="button dark"
            disabled={
              !health?.firms_key_configured || !chosen || busy || active || !puedeAdministrar
            }
            onClick={acquireMonth}
          >
            <CloudDownload size={17} />
            {tr('Download', 'Descargar')} {date}
          </button>
          <p className="small-note">
            {scope === 'world'
              ? tr(
                  'A global monthly download can hold many records. The job runs in the background.',
                  'Una descarga mensual mundial puede contener muchos registros. El trabajo se ejecuta en segundo plano.',
                )
              : tr(
                  'Polygon queries download their bounding rectangle; the analysis then filters the exact geometry.',
                  'Las consultas por polígono descargan su rectángulo envolvente; el análisis filtra después la geometría exacta.',
                )}{' '}
            {tr(
              'Incomplete periods keep that status.',
              'Los períodos incompletos conservan ese estado.',
            )}
          </p>
          <div className="recent-acquisition">
            <div>
              <h3>{tr('Recent global snapshot', 'Instantánea mundial reciente')}</h3>
              <p>
                {tr(
                  'MODIS, NOAA-20 and NOAA-21 · one verified common date.',
                  'MODIS, NOAA-20 y NOAA-21 · una fecha común verificada.',
                )}
              </p>
            </div>
            <button
              className="button outline"
              disabled={!health?.firms_key_configured || busy || active || !puedeAdministrar}
              onClick={recent}
            >
              <RefreshCw size={16} />
              {tr('Request', 'Consultar')}
            </button>
          </div>
        </section>
        <aside className="source-notes">
          <h2>{tr('What is available.', 'Qué está disponible.')}</h2>
          <p>
            {worldStart
              ? tr(
                  `Global archive loaded: ${worldStart.slice(0, 10)} to ${worldEnd?.slice(0, 10)} · ${worldFiles.length} files. The MVP uses 2025–2026, with MODIS and VIIRS kept separate by instrument.`,
                  `Archivo mundial incorporado: ${worldStart.slice(0, 10)} a ${worldEnd?.slice(0, 10)} · ${worldFiles.length} archivos. El MVP utiliza 2025–2026, con MODIS y VIIRS separados por instrumento.`,
                )
              : tr(
                  'The global archive grows with imports and area queries.',
                  'El archivo mundial se amplía con importaciones y consultas por área.',
                )}{' '}
            {tr(
              'The earlier Peruvian history is kept as a regional set. Detection dates do not certify complete observation; months without support never become zero.',
              'El histórico peruano anterior se conserva como conjunto regional. Las fechas de detecciones no certifican observación completa; los meses sin soporte no se convierten en cero.',
            )}
          </p>
          <p>
            {tr(
              'Detections are thermal pixels. Observation coverage and scientific harmonization still await L2 products and validation.',
              'Las detecciones son píxeles térmicos. La cobertura de observación y la armonización científica continúan pendientes de productos L2 y validación.',
            )}
          </p>
          <a href="https://firms.modaps.eosdis.nasa.gov/api/area/" target="_blank" rel="noreferrer">
            {tr('FIRMS documentation', 'Documentación FIRMS')}
            <ArrowUpRight size={15} />
          </a>
          <a href="https://nasa-gibs.github.io/gibs-api-docs/" target="_blank" rel="noreferrer">
            {tr('GIBS reference imagery', 'Imágenes de referencia GIBS')}
            <ArrowUpRight size={15} />
          </a>
          <p className="small-note">
            {tr(
              'World cartography: Natural Earth 110m, public domain. Countries are generalized selections. Peru uses the national FIRMS archive; regions come from geoBoundaries.',
              'Cartografía mundial: Natural Earth 110m, dominio público. Los países son selecciones generalizadas. Perú usa el archivo nacional FIRMS; las regiones provienen de geoBoundaries.',
            )}
          </p>
        </aside>
      </div>
      <section className="jobs-section">
        <h2>{tr('Processing jobs.', 'Trabajos de procesamiento.')}</h2>
        {jobs.length ? (
          <div className="job-list">
            {jobs.map((j) => (
              <div key={j.id} className="job-row">
                {j.status === 'complete' ? <CheckCircle2 size={18} /> : <Clock3 size={18} />}
                <div>
                  <strong>
                    {j.kind === 'archive_month'
                      ? tr('Monthly archive', 'Archivo mensual')
                      : j.kind === 'acquire_world'
                        ? tr('Global snapshot', 'Instantánea mundial')
                        : j.kind}
                  </strong>
                  <p>{j.message}</p>
                  {['queued', 'running'].includes(j.status) && (
                    <progress
                      value={j.progress}
                      max={1}
                      aria-label={tr('Job progress', 'Avance del trabajo')}
                    />
                  )}
                </div>
                <span className={`job-status ${j.status}`}>{jobStatus[j.status] || j.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <p>{tr('No recent jobs.', 'No hay trabajos recientes.')}</p>
        )}
      </section>
      <details className="import-section">
        <summary>{tr('Import your own FIRMS CSV', 'Importar un CSV FIRMS propio')}</summary>
        <div className="upload-form">
          <label>
            {tr('Source', 'Fuente')}
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="modis">MODIS</option>
              <option value="viirs-snpp">VIIRS S-NPP</option>
              <option value="viirs-jpss1">VIIRS NOAA-20</option>
              <option value="viirs-jpss2">VIIRS NOAA-21</option>
            </select>
          </label>
          <label>
            {tr('CSV · up to 200 MB', 'CSV · hasta 200 MB')}
            <input ref={file} type="file" accept=".csv,text/csv" />
          </label>
          <button className="button outline" disabled={busy || !puedeAdministrar} onClick={upload}>
            <Upload size={16} />
            {scope === 'world'
              ? tr('Import for the planet', 'Importar para el planeta')
              : scope === 'PER'
                ? tr('Import for Peru', 'Importar para Perú')
                : tr('Import for this area', 'Importar para esta área')}
          </button>
        </div>
        <p className="small-note">
          {tr(
            'Uses the acquisition scope selected above. The file does not by itself declare that a month or territory is fully observed.',
            'Usa el ámbito de adquisición seleccionado arriba. El archivo no declara por sí mismo que un mes o territorio esté completamente observado.',
          )}
        </p>
      </details>
      <section className="inventory-section">
        <h2>
          {tr(
            'NASA availability for new downloads.',
            'Disponibilidad en NASA para nuevas descargas.',
          )}
        </h2>
        <p className="small-note">
          {catalog?.checked_at
            ? `${tr('Checked', 'Consultado')}: ${new Date(catalog.checked_at).toLocaleString(locale())}${catalog.stale ? tr(' · last check kept', ' · última consulta conservada') : ''}`
            : tr('Availability not verified', 'Disponibilidad sin verificar')}
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{tr('Product', 'Producto')}</th>
                <th>{tr('From', 'Desde')}</th>
                <th>{tr('To', 'Hasta')}</th>
              </tr>
            </thead>
            <tbody>
              {catalog?.products.map((p) => (
                <tr key={p.product}>
                  <td>{p.product}</td>
                  <td>{p.start}</td>
                  <td>{p.end}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="inventory-section">
        <h2>{tr('Loaded files.', 'Archivos incorporados.')}</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{tr('File', 'Archivo')}</th>
                <th>{tr('Scope', 'Ámbito')}</th>
                <th>{tr('Period', 'Período')}</th>
                <th>{tr('New rows', 'Filas nuevas')}</th>
                <th>SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {status?.batches.map((b) => (
                <tr key={b.id}>
                  <td>{b.filename}</td>
                  <td>
                    {b.spatial_scope === 'world'
                      ? tr('Global', 'Mundial')
                      : b.spatial_scope === 'custom'
                        ? tr('Area', 'Área')
                        : tr('Peru', 'Perú')}
                  </td>
                  <td>
                    {b.coverage_start?.slice(0, 10) || tr('Unknown', 'Desconocido')} →{' '}
                    {b.coverage_end?.slice(0, 10) || '—'}
                  </td>
                  <td>{fmt(b.rows_loaded)}</td>
                  <td>
                    <code title={b.sha256}>{b.sha256.slice(0, 12)}…</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
