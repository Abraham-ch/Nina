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
  inpe_agreement: { annual_pearson_2012_2025: number }
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
    names = top.map((d) => title(d.department)).join(', ')
  const cards = [
    {
      figure: `×${number(jump.raw_pixels, 1)} → ×${number(jump.harmonized, 2)}`,
      head: tr('The record broke in 2012', 'El registro se rompió en 2012'),
      body: tr(
        `When VIIRS arrived, Peru's September detections jumped ×${number(jump.raw_pixels, 1)} in raw pixels (2012–2023 against 2003–2011): a change of instrument, not of fire. After harmonization the same comparison gives ×${number(jump.harmonized, 2)}. It breaks again now: S-NPP stopped on 2 November 2026 and MODIS follows.`,
        `Cuando llegó VIIRS, las detecciones de septiembre en el Perú saltaron ×${number(jump.raw_pixels, 1)} en píxeles crudos (2012–2023 frente a 2003–2011): un cambio de instrumento, no de fuego. Tras la armonización, la misma comparación da ×${number(jump.harmonized, 2)}. Se rompe otra vez ahora: S-NPP se detuvo el 2 de noviembre de 2026 y MODIS le sigue.`,
      ),
    },
    {
      figure: tr(
        `#${sept.rank_2003_2025} of ${sept.years_compared}`,
        `${sept.rank_2003_2025}.º de ${sept.years_compared}`,
      ),
      head: tr('September 2024, read in time', 'Septiembre de 2024, leído a tiempo'),
      body: tr(
        `The highest September since 2003, ${number(sept.anomaly_vs_median_snpp_only_2012_2023)} % above the 2012–2023 median (previous record: ${sept.previous_record[1]}).${peru ? ` On 18 September, the day of the emergency decree, the previous 14 days were ${number(peru.on_declaration_day.ratio_to_median, 1)}× the median${peru.above_previous_max_continuously_since ? ` and had been above every year since ${day(peru.above_previous_max_continuously_since)}` : ''}.` : ''}${amazonas ? ` Amazonas was at ${number(amazonas.on_declaration_day.ratio_to_median, 1)}×.` : ''} ${records.length} departments set a September record.`,
        `El septiembre más alto desde 2003, ${number(sept.anomaly_vs_median_snpp_only_2012_2023)} % por encima de la mediana 2012–2023 (récord anterior: ${sept.previous_record[1]}).${peru ? ` El 18 de septiembre, día del decreto de emergencia, los 14 días previos estaban a ${number(peru.on_declaration_day.ratio_to_median, 1)}× la mediana${peru.above_previous_max_continuously_since ? ` y superaban a todos los años desde el ${day(peru.above_previous_max_continuously_since)}` : ''}.` : ''}${amazonas ? ` Amazonas estaba a ${number(amazonas.on_declaration_day.ratio_to_median, 1)}×.` : ''} ${records.length} departamentos marcaron récord de septiembre.`,
      ),
    },
    {
      figure: `${share(topDetected)} / ${share(topReported)}`,
      head: tr('Detected is not reported', 'Detectado no es reportado'),
      body: tr(
        `Reported forest-fire emergencies (INDECI) grew ×${number(dvr.reported_growth_2019_2023_vs_2003_2007)} between 2003–2007 and 2019–2023, while detected activity changed ×${number(dvr.detected_growth_2019_2023_vs_2003_2007, 2)}. In 2024, ${names} held ${share(topDetected)} of the activity detected in Peru and ${share(topReported)} of the reported emergencies.`,
        `Las emergencias por incendio forestal reportadas (INDECI) crecieron ×${number(dvr.reported_growth_2019_2023_vs_2003_2007)} entre 2003–2007 y 2019–2023, mientras la actividad detectada cambió ×${number(dvr.detected_growth_2019_2023_vs_2003_2007, 2)}. En 2024, ${names} concentraron el ${share(topDetected)} de la actividad detectada en el Perú y el ${share(topReported)} de las emergencias reportadas.`,
      ),
    },
    {
      figure: `r = ${number(e.inpe_agreement.annual_pearson_2012_2025, 2)}`,
      head: tr('Checked against another instrument', 'Contrastado con otro instrumento'),
      body: tr(
        `INPE's series (MODIS Aqua only) and NINA's agree year to year with r = ${number(e.inpe_agreement.annual_pearson_2012_2025, 2)} in 2012–2025. NINA is not a forecast: July–August anticipates an above-normal September ${share(e.prediction_hindcast.national_hit_rate)} of the time, against ${share(e.prediction_hindcast.chance_level)} by chance.`,
        `La serie del INPE (solo MODIS Aqua) y la de NINA coinciden año a año con r = ${number(e.inpe_agreement.annual_pearson_2012_2025, 2)} en 2012–2025. NINA no es un pronóstico: julio–agosto anticipa un septiembre por encima de lo normal el ${share(e.prediction_hindcast.national_hit_rate)} de las veces, frente al ${share(e.prediction_hindcast.chance_level)} por azar.`,
      ),
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
          'One 25-year series across satellites, so anyone can see whether this season is unusual, where, and where burning goes unreported.',
          'Una serie de 25 años entre satélites, para que cualquiera vea si esta temporada es inusual, dónde, y dónde se quema sin que se reporte.',
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
                  `About ${share(w.archive_share)} of NASA's archived fire detections, from the Amazon to Siberia, each country and ecosystem with its own conversion.`,
                  `Cerca del ${share(w.archive_share)} de las detecciones de fuego archivadas por la NASA, de la Amazonía a Siberia, cada país y ecosistema con su propia conversión.`,
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
                  `Median change after VIIRS arrives in ${w.break_2012.countries} countries: raw counts versus NINA.`,
                  `Cambio mediano tras la llegada de VIIRS en ${w.break_2012.countries} países: conteo crudo frente a NINA.`,
                )}
              </p>
            </li>
            <li>
              <span className="landing-evidence-figure">{share(w.modis_gate.fraction)}</span>
              <strong>{tr('of country–ecosystem pairs pass', 'de los pares país–ecosistema aprueban')}</strong>
              <p>
                {tr(
                  `${w.modis_gate.passed} of ${w.modis_gate.evaluable} pass a bar set in advance (80 %), checking each year with a conversion that never used it; typical difference ${share(w.modis_gate.typical_year_error)}.`,
                  `${w.modis_gate.passed} de ${w.modis_gate.evaluable} superan una meta fijada de antemano (80 %), comprobando cada año con una conversión que no lo usó; diferencia típica ${share(w.modis_gate.typical_year_error)}.`,
                )}
              </p>
            </li>
            {w.registries.Canada && (
              <li>
                <span className="landing-evidence-figure">{share(w.registries.Canada.rate)}</span>
                <strong>{tr('of recorded wildfires found', 'de los incendios registrados, encontrados')}</strong>
                <p>
                  {tr(
                    `Canada's official database: large wildfires that NINA also detects (${number(100 * w.registries.Canada.chance_rate, 1)} % by chance).`,
                    `Base oficial de Canadá: incendios grandes que NINA también detecta (${number(100 * w.registries.Canada.chance_rate, 1)} % por azar).`,
                  )}
                </p>
              </li>
            )}
          </ul>
        </>
      )}
      <p className="landing-caveat">
        {tr(
          `Unit: VIIRS-equivalent active cell-days (one ~5 km² H3 cell with at least one valid detection in a day), not fires or burned area. Method ${e.method_version}, dataset ${e.dataset_id}. The harmonization is experimental: it has not passed every scientific validation gate. A retrospective reading, not a tested alert.`,
          `Unidad: celdas-día activas equivalentes VIIRS (una celda H3 de ~5 km² con al menos una detección válida en un día), no incendios ni área quemada. Método ${e.method_version}, conjunto ${e.dataset_id}. La armonización es experimental: no ha superado todas las pruebas de validación científica. Es una lectura retrospectiva, no una alerta probada.`,
        )}
      </p>
    </section>
  )
}
