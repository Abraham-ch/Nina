import ExperimentalTag from '../ExperimentalTag'
import { locale, tr } from '../i18n'

// Static summary built by scripts/evidence/peru_case.py (docs/PROBLEM.md); only the fields shown here.
type Replay = {
  label: string
  on_declaration_day: { ratio_to_median: number }
  above_previous_max_continuously_since: string | null
}
export type PeruEvidence = {
  dataset_id: string
  method_version: string
  september_mean_ratio_2012_2023_vs_2003_2011: { raw_pixels: number; harmonized: number }
  september_2024: {
    rank_2003_2025: number
    years_compared: number
    anomaly_vs_median_snpp_only_2012_2023: number
    previous_record: [number, number]
  }
  replay_2024: Replay[]
  department_records_september_2024: { department: string; record: boolean }[]
  prediction_hindcast: { national_hit_rate: number; chance_level: number }
  detected_vs_reported: {
    reported_growth_2019_2023_vs_2003_2007: number
    detected_growth_2019_2023_vs_2003_2007: number
    departments_2024: { department: string; detected_share: number; reported_share: number }[]
  }
  inpe_agreement: {
    annual_pearson_2012_2025: number
    top_septembers_inpe?: number[]
    top_septembers_nina?: number[]
  }
  human_cost?: {
    september_2024: HumanCount
    before_decree_2024: HumanCount
    year_2024: HumanCount
    all_years: HumanCount & { first_year: number; last_year: number }
  }
}
type HumanCount = {
  emergencies: number
  departments: number
  deaths: number
  injured: number
  homeless: number
  affected: number
}

// Global summary built by scripts/evidence/world_evidence.py from the 0.5.0 run.
export type WorldEvidence = {
  countries: number
  archive_share: number
  modis_gate: { passed: number; evaluable: number; fraction: number; strict_fraction: number; typical_year_error: number }
  outside_calibration_bias: { now: number; with_five_countries: number | null }
  break_2012: { countries: number; median_raw_pixels_ratio: number; median_harmonized_ratio: number }
  registries: Record<string, { rate: number; chance_rate: number; records: number }>
}

const number = (n: number, digits = 0) =>
  n.toLocaleString(locale(), { maximumFractionDigits: digits, minimumFractionDigits: digits })
export const share = (n: number) => `${Math.round(n * 100)} %`
export const title = (name: string) =>
  name
    .toLowerCase()
    .replace(/(^|\s)\p{L}/gu, (c) => c.toUpperCase())
    .replace('San Martin', 'San Martín')
export const day = (iso: string) =>
  new Date(iso + 'T00:00:00Z').toLocaleDateString(locale(), {
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  })

/** The problem in figures (docs/PROBLEM.md), read from the reproducible Peru evidence. */
export default function Evidence({ e, w }: { e: PeruEvidence | null; w?: WorldEvidence | null }) {
  if (!e) return null
  const jump = e.september_mean_ratio_2012_2023_vs_2003_2011,
    sept = e.september_2024,
    peru = e.replay_2024.find((r) => r.label === 'Peru'),
    amazonas = e.replay_2024.find((r) => r.label === 'Amazonas'),
    records = e.department_records_september_2024.filter((d) => d.record).map((d) => d.department),
    dvr = e.detected_vs_reported,
    top = [...dvr.departments_2024].sort((a, b) => b.detected_share - a.detected_share).slice(0, 3),
    topDetected = top.reduce((s, d) => s + d.detected_share, 0),
    topReported = top.reduce((s, d) => s + d.reported_share, 0),
    names = top.map((d) => title(d.department)).join(', '),
    inpeTop = e.inpe_agreement.top_septembers_inpe ?? [],
    ninaTop = e.inpe_agreement.top_septembers_nina ?? [],
    sameTop = inpeTop.filter((y) => ninaTop.includes(y)).length
  const cards = [
    {
      figure: `×${number(jump.raw_pixels, 1)} → ×${number(jump.harmonized, 1)}`,
      head: tr('A fake jump in 2012', 'Un salto falso en 2012'),
      body: tr(
        `A sharper satellite camera made Peru's fire seem to multiply ×${number(jump.raw_pixels, 1)} overnight. NINA removes the jump.`,
        `Una cámara satelital más fina hizo que el fuego del Perú pareciera multiplicarse ×${number(jump.raw_pixels, 1)} de golpe. NINA elimina el salto.`,
      ),
    },
    {
      figure: `+${number(sept.anomaly_vs_median_snpp_only_2012_2023)} %`,
      head: tr(`September 2024, the worst in ${sept.years_compared} years`, `Septiembre de 2024, el peor en ${sept.years_compared} años`),
      body: tr(
        `More fire than a normal September; ${records.length} regions had their worst September on record.`,
        `Más fuego que un septiembre normal; ${records.length} regiones tuvieron su peor septiembre registrado.`,
      ),
    },
    {
      figure: `${share(topDetected)} / ${share(topReported)}`,
      head: tr('Where it burns most, it is reported least', 'Donde más arde, menos se reporta'),
      body: tr(
        `In 2024, ${names}: ${share(topDetected)} of the fire seen from space, ${share(topReported)} of the emergencies reported.`,
        `En 2024, ${names}: el ${share(topDetected)} del fuego visto desde el espacio, el ${share(topReported)} de las emergencias reportadas.`,
      ),
    },
    {
      figure: inpeTop.length ? `${sameTop} / ${inpeTop.length}` : `r = ${number(e.inpe_agreement.annual_pearson_2012_2025, 2)}`,
      head: tr("Brazil's space agency agrees", 'La agencia espacial de Brasil coincide'),
      body: inpeTop.length
        ? tr(
            `INPE, with its own method, ranks the same worst Septembers: ${inpeTop.join(', ')}.`,
            `El INPE, con su propio método, ordena los mismos peores septiembres: ${inpeTop.join(', ')}.`,
          )
        : tr('INPE, with its own method, ranks the years the same way.', 'El INPE, con su propio método, ordena los años del mismo modo.'),
    },
  ]
  return (
    <section className="landing-evidence" aria-labelledby="landing-evidence-title">
      <p className="landing-kicker">
        {tr(
          'The problem · harmonized MODIS + VIIRS archive',
          'El problema · archivo armonizado MODIS + VIIRS',
        )}
        <ExperimentalTag />
      </p>
      <h2 id="landing-evidence-title">
        {tr(
          "Peru's fire record broke twice. NINA keeps one consistent record.",
          'El registro de incendios del Perú se rompió dos veces. NINA mantiene uno coherente.',
        )}
      </h2>
      <p className="landing-evidence-lead">
        {tr(
          'One record across satellites, 25 years long: is this season unusual, and where?',
          'Un registro entre satélites, de 25 años: ¿esta temporada es inusual, y dónde?',
        )}
      </p>
      <ul className="landing-evidence-cards">
        {cards.map((c) => (
          <li key={c.head}>
            <span className="landing-evidence-figure">{c.figure}</span>
            <strong>{c.head}</strong>
            <p>{c.body}</p>
          </li>
        ))}
      </ul>
      {w && (
        <>
          <h3 className="landing-evidence-subtitle">
            {tr(
              `Beyond Peru: the same record in ${w.countries} countries`,
              `Más allá del Perú: el mismo registro en ${w.countries} países`,
            )}
          </h3>
          <ul className="landing-evidence-cards">
            <li>
              <span className="landing-evidence-figure">{w.countries}</span>
              <strong>{tr('countries, calibrated one by one', 'países, calibrados uno por uno')}</strong>
              <p>
                {tr(
                  `About ${share(w.archive_share)} of NASA's fire archive, from the Amazon to Siberia.`,
                  `Cerca del ${share(w.archive_share)} del archivo de fuego de la NASA, de la Amazonía a Siberia.`,
                )}
              </p>
            </li>
            <li>
              <span className="landing-evidence-figure">
                ×{number(w.break_2012.median_raw_pixels_ratio, 1)} → ×{number(w.break_2012.median_harmonized_ratio, 1)}
              </span>
              <strong>{tr('the 2012 jump, removed', 'el salto de 2012, eliminado')}</strong>
              <p>
                {tr(
                  `Typical jump in ${w.break_2012.countries} countries: raw counts, then NINA.`,
                  `Salto típico en ${w.break_2012.countries} países: conteo crudo, luego NINA.`,
                )}
              </p>
            </li>
            <li>
              <span className="landing-evidence-figure">{share(w.modis_gate.fraction)}</span>
              <strong>{tr('of country–ecosystem pairs pass', 'de los pares país–ecosistema aprueban')}</strong>
              <p>
                {tr(
                  `${w.modis_gate.passed} of ${w.modis_gate.evaluable} tests pass a bar set in advance.`,
                  `${w.modis_gate.passed} de ${w.modis_gate.evaluable} pruebas superan una meta fijada de antemano.`,
                )}
              </p>
            </li>
            {w.registries.Canada && (
              <li>
                <span className="landing-evidence-figure">{share(w.registries.Canada.rate)}</span>
                <strong>{tr('of recorded wildfires found', 'de los incendios registrados, encontrados')}</strong>
                <p>
                  {tr(
                    `Large wildfires in Canada's official records that NINA also finds.`,
                    `Incendios grandes de los registros oficiales de Canadá que NINA también encuentra.`,
                  )}
                </p>
              </li>
            )}
          </ul>
        </>
      )}
      <p className="landing-caveat">
        {tr(
          `Unit: ~5 km² squares with fire per day (VIIRS scale), not fires or hectares. Method ${e.method_version}, experimental. A reading of the past, not an alert. Human figures: INDECI.`,
          `Unidad: cuadros de ~5 km² con fuego por día (escala VIIRS), no incendios ni hectáreas. Método ${e.method_version}, experimental. Una lectura del pasado, no una alerta. Cifras humanas: INDECI.`,
        )}
      </p>
    </section>
  )
}
