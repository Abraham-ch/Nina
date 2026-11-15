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
  this_year?: ThisYearFigures
}
type ThisYearFigures = {
  year: number
  through_month: number
  countries_with_record_month: number
  records_by_country: { country: string; month: number; times_median: number; provisional: boolean }[]
  peru_september: { anomaly_percent: number; rank: number; rank_of: number; provisional: boolean }
  chilecito_july: { value: number; median: number; rank: number; rank_of: number }
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

type Card = { figure: string; head: string; body: string }

function Cards({ cards }: { cards: Card[] }) {
  return (
    <ul className={`landing-evidence-cards${cards.length === 3 ? ' three' : ''}`}>
      {cards.map((c) => (
        <li key={c.head}>
          <span className="landing-evidence-figure">{c.figure}</span>
          <strong>{c.head}</strong>
          <p>{c.body}</p>
        </li>
      ))}
    </ul>
  )
}

// Spanish names of the 31 calibration countries (Natural Earth names, as the product stores them).
const COUNTRY_ES: Record<string, string> = {
  Brazil: 'Brasil', Canada: 'Canadá', 'Dem. Rep. Congo': 'R. D. del Congo', Ethiopia: 'Etiopía', Greece: 'Grecia',
  Indonesia: 'Indonesia', Kazakhstan: 'Kazajistán', Mexico: 'México', Myanmar: 'Birmania', Peru: 'Perú',
  Russia: 'Rusia', 'South Africa': 'Sudáfrica', Spain: 'España', Turkey: 'Turquía',
  'United States of America': 'Estados Unidos', Zambia: 'Zambia',
}
const countryName = (name: string) => tr(name === 'United States of America' ? 'United States' : name, COUNTRY_ES[name] ?? name)

/** Chapter 1 · the problem: why "is this season normal?" has no answer today. */
export function Problem({ e }: { e: PeruEvidence | null }) {
  if (!e) return null
  const jump = e.september_mean_ratio_2012_2023_vs_2003_2011
  return (
    <section className="landing-evidence" aria-labelledby="landing-problem-title">
      <p className="landing-kicker">{tr('1 · The problem', '1 · El problema')}</p>
      <h2 id="landing-problem-title">
        {tr('In 2012 the satellite camera changed. The fire did not.', 'En 2012 cambió la cámara del satélite. El fuego no.')}
      </h2>
      <p className="landing-evidence-lead">
        {tr(
          'So no one can say with satellite data whether a fire season is normal.',
          'Por eso nadie puede decir con datos satelitales si una temporada de incendios es normal.',
        )}
      </p>
      <Cards
        cards={[
          {
            figure: `×${number(jump.raw_pixels, 1)}`,
            head: tr('A fake jump in 2012', 'Un salto falso en 2012'),
            body: tr(
              `A sharper camera made Peru's fire seem to multiply ×${number(jump.raw_pixels, 1)} overnight. In NINA's record: ×${number(jump.harmonized, 1)}.`,
              `Una cámara más fina hizo que el fuego del Perú pareciera multiplicarse ×${number(jump.raw_pixels, 1)} de golpe. En el registro de NINA: ×${number(jump.harmonized, 1)}.`,
            ),
          },
          {
            figure: tr('2 Nov 2026', '2 nov 2026'),
            head: tr('And it is happening again', 'Y está pasando otra vez'),
            body: tr(
              'One VIIRS satellite stopped and MODIS is retiring. Without a bridge, 25 years of history stop being comparable.',
              'Un satélite VIIRS se detuvo y MODIS se retira. Sin un puente, 25 años de historia dejan de ser comparables.',
            ),
          },
        ]}
      />
    </section>
  )
}

/** Chapter 4 · this year: the same question answered for the current season, in both directions. */
export function ThisYear({ w }: { w?: WorldEvidence | null }) {
  const t = w?.this_year
  if (!w || !t) return null
  const names = t.records_by_country.map((r) => countryName(r.country))
  const peru = t.peru_september
  const chile = t.chilecito_july
  return (
    <section className="landing-evidence" aria-labelledby="landing-year-title">
      <p className="landing-kicker">{tr(`4 · ${t.year}, this year`, `4 · ${t.year}, este año`)}</p>
      <h2 id="landing-year-title">
        {tr('Is this season normal? Now there is an answer.', '¿Esta temporada es normal? Ahora hay respuesta.')}
      </h2>
      <Cards
        cards={[
          {
            figure: `${t.countries_with_record_month} / ${w.countries}`,
            head: tr('countries with a record month', 'países con un mes récord'),
            body: tr(
              `More fire than in the same month of any year since 2003: ${names.join(', ')}.`,
              `Más fuego que en el mismo mes de cualquier año desde 2003: ${names.join(', ')}.`,
            ),
          },
          {
            figure: `×${number(chile.value / chile.median, 0)}`,
            head: tr("The challenge's own example", 'El ejemplo del propio desafío'),
            body: tr(
              `Chilecito, Argentina: July ${t.year} had ${number(chile.value / chile.median, 0)} times the fire of a normal July, the most in ${chile.rank_of} years.`,
              `Chilecito, Argentina: julio de ${t.year} tuvo ${number(chile.value / chile.median, 0)} veces el fuego de un julio normal, el mayor en ${chile.rank_of} años.`,
            ),
          },
          {
            figure: `${number(peru.anomaly_percent)} %`,
            head: tr('Peru, a calm September', 'Perú, un septiembre tranquilo'),
            body: tr(
              `NINA also says when a season is normal: September ${t.year} had less fire than a normal September.`,
              `NINA también dice cuándo una temporada es normal: septiembre de ${t.year} tuvo menos fuego que un septiembre normal.`,
            ),
          },
        ]}
      />
      <p className="landing-caveat">
        {tr(
          `${t.year} values come from near-real-time data and are provisional.`,
          `Los valores de ${t.year} vienen de datos casi en tiempo real y son provisionales.`,
        )}
      </p>
    </section>
  )
}

/** Chapter 5 · why trust it: independent checks of the record. */
export default function Evidence({ e, w }: { e: PeruEvidence | null; w?: WorldEvidence | null }) {
  if (!e) return null
  const inpeTop = e.inpe_agreement.top_septembers_inpe ?? [],
    ninaTop = e.inpe_agreement.top_septembers_nina ?? [],
    sameTop = inpeTop.filter((y) => ninaTop.includes(y)).length
  const cards: Card[] = []
  if (w) {
    cards.push(
      {
        figure: share(w.modis_gate.fraction),
        head: tr('of the tests pass', 'de las pruebas aprueban'),
        body: tr(
          `In ${w.countries} countries, the old satellite converted by NINA matches what the new one saw: ${w.modis_gate.passed} of ${w.modis_gate.evaluable} tests, with a bar set in advance.`,
          `En ${w.countries} países, el satélite antiguo convertido por NINA coincide con lo que vio el nuevo: ${w.modis_gate.passed} de ${w.modis_gate.evaluable} pruebas, con una meta fijada de antemano.`,
        ),
      },
      {
        figure: `×${number(w.break_2012.median_raw_pixels_ratio, 1)} → ×${number(w.break_2012.median_harmonized_ratio, 1)}`,
        head: tr('the fake 2012 jump, removed', 'el salto falso de 2012, eliminado'),
        body: tr(
          `Typical change when the new satellite arrived, in ${w.break_2012.countries} countries: raw counts, then NINA.`,
          `Cambio típico al llegar el satélite nuevo, en ${w.break_2012.countries} países: conteo crudo, luego NINA.`,
        ),
      },
    )
    if (w.registries.Canada)
      cards.push({
        figure: share(w.registries.Canada.rate),
        head: tr('of recorded wildfires found', 'de los incendios registrados, encontrados'),
        body: tr(
          "Large wildfires in Canada's official records that NINA also finds.",
          'Incendios grandes de los registros oficiales de Canadá que NINA también encuentra.',
        ),
      })
  }
  cards.push({
    figure: inpeTop.length ? `${sameTop} / ${inpeTop.length}` : `r = ${number(e.inpe_agreement.annual_pearson_2012_2025, 2)}`,
    head: tr("Brazil's space agency agrees", 'La agencia espacial de Brasil coincide'),
    body: inpeTop.length
      ? tr(
          `INPE, with its own method, ranks the same worst Septembers for Peru: ${inpeTop.join(', ')}.`,
          `El INPE, con su propio método, ordena los mismos peores septiembres del Perú: ${inpeTop.join(', ')}.`,
        )
      : tr('INPE, with its own method, ranks the years the same way.', 'El INPE, con su propio método, ordena los años del mismo modo.'),
  })
  return (
    <section className="landing-evidence" aria-labelledby="landing-evidence-title">
      <p className="landing-kicker">
        {tr('5 · Why trust it', '5 · Por qué confiar')}
        <ExperimentalTag />
      </p>
      <h2 id="landing-evidence-title">
        {tr('Checked against what really happened.', 'Contrastado con lo que de verdad pasó.')}
      </h2>
      <Cards cards={cards} />
      <p className="landing-caveat">
        {tr(
          `Unit: ~5 km² squares with fire per day (VIIRS scale), not fires or hectares. Method ${e.method_version}, experimental. A reading of the past, not an alert. Human figures: INDECI.`,
          `Unidad: cuadros de ~5 km² con fuego por día (escala VIIRS), no incendios ni hectáreas. Método ${e.method_version}, experimental. Una lectura del pasado, no una alerta. Cifras humanas: INDECI.`,
        )}
      </p>
    </section>
  )
}
