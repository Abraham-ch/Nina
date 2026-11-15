import { ArrowRight, Eye, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api, fmt, months } from './api'
import { tr } from './i18n'
import type { Experiment as Result, Regions } from './types'

export default function Experiment({
  regions,
}: {
  regions: Regions | null
}) {
  const [source, setSource] = useState('viirs-snpp'),
    [department, setDepartment] = useState(''),
    [result, setResult] = useState<Result | null>(null),
    [index, setIndex] = useState(0),
    [revealed, setRevealed] = useState(false),
    [error, setError] = useState('')
  useEffect(() => {
    const abort = new AbortController()
    setResult(null)
    setError('')
    api<Result>(
      `/experiments/substitution?source=${source}${department ? '&department=' + encodeURIComponent(department) : ''}`,
      { signal: abort.signal },
    )
      .then((r) => {
        setResult(r)
        setIndex(Math.min(8, Math.max(0, r.samples.length - 1)))
        setRevealed(false)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => abort.abort()
  }, [source, department])
  const sample = result?.samples[index],
    maximum = Math.max(1, sample?.input || 0, sample?.reference || 0, sample?.estimate || 0)
  return (
    <section id="substitution" className="experiment-section">
      <div className="experiment-intro">
        <span className="kicker">
          {tr('An experiment you can check', 'Un experimento que puedes comprobar')}
        </span>
        <h2>
          {tr('We hide one observer.', 'Ocultamos un observador.')}
          <br />
          {tr('Can we rebuild its signal?', '¿Podemos reconstruir su señal?')}
        </h2>
        <p>
          {tr(
            'The model receives VIIRS counts from a held-out period and estimates the Aqua reference. Then you can reveal the original record and review the error.',
            'El modelo recibe conteos VIIRS de un período reservado y estima la referencia Aqua. Después puedes revelar el registro original y revisar el error.',
          )}
        </p>
        <p className="science-label">
          {tr(
            'Validation case: Peru · exploratory count calibration. Valid observation opportunities have not been reconstructed yet.',
            'Caso de validación: Perú · calibración exploratoria de conteos. Las oportunidades válidas aún no se han reconstruido.',
          )}
        </p>
        <div className="experiment-filters">
          <label>
            {tr('Input instrument', 'Instrumento de entrada')}
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="viirs-snpp">VIIRS · S-NPP</option>
              <option value="viirs-jpss1">VIIRS · NOAA-20</option>
            </select>
          </label>
          <label>
            {tr('Test region', 'Región de prueba')}
            <select
              value={department || result?.department || ''}
              onChange={(e) => setDepartment(e.target.value)}
            >
              {regions?.geojson.features.map((f) => (
                <option value={f.properties.id} key={f.properties.id}>
                  {f.properties.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="experiment-method">
          <span>
            {tr('Training', 'Entrenamiento')}
            <strong>2018–2022</strong>
          </span>
          <ArrowRight size={17} />
          <span>
            {tr('Validation', 'Validación')}
            <strong>2023</strong>
          </span>
          <ArrowRight size={17} />
          <span>
            {tr('Held-out test', 'Prueba reservada')}
            <strong>2024–2025</strong>
          </span>
        </div>
      </div>
      <div className="experiment-result" aria-live="polite">
        {sample ? (
          <>
            <div className="experiment-title">
              <span>{result?.area_name}</span>
              <strong>
                {months()[sample.month - 1]} {sample.year}
              </strong>
            </div>
            <label className="sample-picker">
              {tr('Held-out month', 'Mes reservado')}
              <input
                aria-label={tr('Held-out experiment month', 'Mes del experimento reservado')}
                type="range"
                min={0}
                max={(result?.samples.length || 1) - 1}
                value={index}
                onChange={(e) => {
                  setIndex(Number(e.target.value))
                  setRevealed(false)
                }}
              />
            </label>
            <div className="experiment-bars">
              {[
                [tr('VIIRS input', 'Entrada VIIRS'), sample.input, 'input'],
                [tr('Aqua estimate', 'Estimación de Aqua'), sample.estimate, 'estimate'],
                [
                  tr('Held-out Aqua reference', 'Referencia Aqua reservada'),
                  revealed ? sample.reference : null,
                  'reference',
                ],
              ].map(([label, value, kind]) => (
                <div className={`experiment-bar ${kind}`} key={String(kind)}>
                  <div>
                    <span>{label}</span>
                    <strong>
                      {value == null
                        ? tr('To be revealed', 'Por revelar')
                        : fmt(Number(value), kind === 'estimate' ? 1 : 0)}
                    </strong>
                  </div>
                  <div className="bar-track">
                    <div
                      style={{
                        width: value == null ? '0%' : `${(Number(value) / maximum) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            {revealed ? (
              <div className="revealed-result">
                <span>
                  {tr('Absolute error in this case', 'Error absoluto en este caso')}
                  <strong>
                    {fmt(sample.absolute_error, 2)} {tr('detections', 'detecciones')}
                  </strong>
                </span>
                <button className="text-link" onClick={() => setRevealed(false)}>
                  <RotateCcw size={15} />
                  {tr('Hide reference', 'Ocultar referencia')}
                </button>
              </div>
            ) : (
              <button className="button dark" onClick={() => setRevealed(true)}>
                <Eye size={16} />
                {tr('Reveal the reference', 'Revelar la referencia')}
              </button>
            )}
            <p className="experiment-footnote">
              {fmt(result?.samples.length)}{' '}
              {tr(
                'pairs in this case · mean absolute error:',
                'pares del caso · error absoluto medio:',
              )}{' '}
              {fmt(result?.mae, 2)}.{' '}
              {result?.region_reserved
                ? tr(
                    'The region was also held out from training.',
                    'La región también se reservó del entrenamiento.',
                  )
                : tr(
                    'This test is split by time.',
                    'La separación de esta prueba es temporal.',
                  )}{' '}
              {tr(
                'It evaluates fit to the archive, without correcting for clouds or exposure.',
                'Se evalúa ajuste al archivo, sin corregir nubes ni exposición.',
              )}
            </p>
            <details>
              <summary>{tr('See method and limits', 'Ver método y límites')}</summary>
              <p>
                {tr(
                  'Poisson regression with the VIIRS count and seasonal terms, compared with a simple factor. Only positive pairs available in the archive are shown. The Aqua reference is not read as all the fire that exists.',
                  'Regresión Poisson con conteo VIIRS y términos estacionales, comparada con un factor simple. Solo se muestran pares positivos disponibles en el archivo. No se interpreta la referencia Aqua como todo el fuego existente.',
                )}
              </p>
              <code>
                {tr('Model', 'Modelo')} {result?.model_id}
              </code>
            </details>
          </>
        ) : (
          <p>
            {error ||
              result?.reason ||
              tr('Querying the experiment…', 'Consultando el experimento…')}
          </p>
        )}
      </div>
    </section>
  )
}
