export type Geometry = {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: number[][][] | number[][][][]
}
export type Selection = {
  scope: 'PER' | 'world' | 'custom'
  area_label: string
  department: string
  source: string
  platform: string
  year_start: number
  year_end: number
  selected_year: number
  selected_month: number
  metric: 'observed' | 'experimental'
  daynight: string
  fire_type: string
  geometry: Geometry | null
}
export type Month = {
  year: number
  month: number
  value: number | null
  observed: number | null
  historical_median: number | null
  historical_n: number
  anomaly_percent: number | null
  status: string
  coverage_percent: null
}
export type Analysis = {
  id: string
  area_name: string
  metric_label: string
  selection: Selection
  selected: Month
  months: Month[]
  limitations: string[]
  references: string[]
  data_revision: string
  software_revision: string
  archive_windows: {
    start: string
    end: string
    basis: string
    scope: string
  }[]
  harmonization_status: string
  synthetic: false
}
export type Place = {
  type: 'Feature'
  id?: string
  geometry: Geometry
  properties: { id: string; name: string }
}
export type Places = { type: 'FeatureCollection'; features: Place[] }
export type Regions = {
  geojson: Places
  provenance: {
    boundarySource: string
    boundaryYearRepresented: string
    boundaryLicense: string
  }
}
export type Point = {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: {
    id: string
    source: string
    platform: string
    date: string
    frp: number | null
    confidence: string
    daynight: string
    scan: number | null
    track: number | null
  }
}
export type Points = {
  type: 'FeatureCollection'
  features: Point[]
  shown: number
  total: number
  sampling: string
  synthetic: false
}
export type Layer = {
  source: string
  platform: string
  selected: Month
  points: Points
  analysis_id: string
}
export type Comparison = {
  layers: Layer[]
  note: string
  synthetic: false
  harmonized: false
}
export type Batch = {
  id: string
  sha256: string
  filename: string
  source: string
  bytes: number
  rows_loaded: number
  rejected: number
  duplicates: number
  url: string
  coverage_start: string
  coverage_end: string
  coverage_basis: string
  spatial_scope: string
}
export type Status = {
  observations: number
  first_date: string
  last_date: string
  database_bytes: number
  unassigned_department: number
  sources: {
    source: string
    platform: string
    count: number
    first_date: string
    last_date: string
  }[]
  batches: Batch[]
}
export type Health = {
  version: string
  scope: string
  firms_key_configured: boolean
  earthdata_configured: boolean
  llm_configured: boolean
}
export type Catalog = {
  products: { product: string; source: string; start: string; end: string }[]
  checked_at: string | null
  stale?: boolean
  configured: boolean
}
export type Reply = {
  answer: string
  framing: string | null
  guidance: string
  engine: string
  evidence: { id: string; label: string; value: unknown }[]
  references: string[]
}
export type Job = {
  id: string
  kind: string
  status: string
  message: string
  progress: number
  result: string | null
}
export type Experiment = {
  available: boolean
  reason?: string
  source: string
  department: string
  area_name: string
  model_id: string
  region_reserved: boolean
  training_years: string
  test_years: string
  mae: number | null
  samples: {
    year: number
    month: number
    input: number
    reference: number
    estimate: number
    baseline: number
    absolute_error: number
  }[]
  limitations: string[]
}
export type Role = 'visitante' | 'analista' | 'admin'
export type User = {
  id: string
  email: string
  role: Role
  display_name: string | null
  created_at: string
}
export type Register = {
  email: string
  password: string
  role: Role
  display_name?: string
}
export type Login = { email: string; password: string }
export type Download = {
  id: string
  user_id: string
  analysis_id: string
  kind: string
  rows: number
  filters: string
  dataset_version: string | null
  created_at: string
}
export type AuditEntry = {
  id: string
  user_id: string
  action: string
  target: string | null
  detail: string | null
  created_at: string
}
// Harmonized product (/api/harmonization, /api/harmonized/*): see docs/HARMONIZED_CONTRACT.md.
export type Readiness = {
  available: boolean
  status: string
  method_version?: string
  scientifically_validated?: boolean
  unit?: string
  as_of_date?: string
}
export type HarmonizedMonth = {
  year: number
  month: number
  value: number | null
  observed_activity: number | null
  unit: string
  status: string
  data_gap: boolean
  partial_coverage: boolean
  is_provisional: boolean
  historical_median: number | null
  historical_n: number
  historical_p10: number | null
  historical_p90: number | null
  anomaly_percent: number | null
  rank: number | null
  rank_of: number
}
export type HarmonizedSelection = {
  country: string
  year_start: number
  year_end: number
  selected_year: number
  selected_month: number
  geometry: Geometry | null
}
export type HarmonizedAnalysis = {
  id: string
  dataset_id: string
  method_version: string
  selection: HarmonizedSelection
  unit: string
  selected: HarmonizedMonth
  months: HarmonizedMonth[]
  scientifically_validated: boolean
  validation_status: string
  legal: string
  limitations: string[]
  references: string[]
  excluded_border_countries: string[]
  synthetic: false
}
export type HarmonizedPoints = {
  type: 'FeatureCollection'
  total: number
  shown: number
  sampled: boolean
  features: {
    type: 'Feature'
    geometry: { type: 'Point'; coordinates: [number, number] }
    properties: {
      cell: string
      activity: number
      calibration_validated: boolean
      observed_cell_days: number
      first_day?: string
      last_day?: string
    }
  }[]
}
export type HarmonizedReply = {
  answer: string
  analysis_id: string
  dataset_id: string
  references: string[]
}
// Territorial evidence report (POST /api/reports/territorial). Only the fields the interface uses.
export type ReportRequest = {
  country: string
  ubigeo?: string | null
  geometry?: Geometry | null
  place_name?: string | null
  year: number
  month: number
  language: 'en' | 'es'
}
// Analytical assistant (POST /api/analyst): answers are checked against the tool results.
export type AnalystTurn = { role: 'user' | 'assistant'; content: string }
export type AnalystQuestion = {
  question: string
  language: 'en' | 'es'
  context: ReportRequest
  history: AnalystTurn[]
}
export type AnalystAnswer = {
  answer: string
  engine: 'deterministic' | 'claude'
  model: string | null
  intent: string
  abstained: boolean
  facts: { label: string; value: string; tool: string }[]
  tools: { name: string; input: Record<string, unknown>; ok: boolean }[]
  verification: { checked: number; unverified: string[]; passed: boolean }
  report_id: string | null
  dataset_id: string
  validation_status: 'validated' | 'experimental'
  notice: string | null
  visuals: AnalystVisual[]
  actions: AnalystAction[]
  follow_ups: string[]
  sources: { title: string; url: string; cited_text: string }[]
}
// Charts and tables of an answer: built by the server from NINA's results, never typed by the model.
export type AnalystVisual = {
  id: string
  kind: string
  type: 'chart' | 'table'
  chart: 'line' | 'bar' | null
  title: string
  unit: string | null
  categories: string[]
  series: { name: string; values: (number | null)[] }[]
  reference_value: number | null
  reference_label: string | null
  highlight: string | null
  columns: string[]
  rows: (string | number | null)[][]
  note: string | null
  source: string
}
// Interface actions offered as buttons; the user presses them, the assistant never does.
export type AnalystAction = {
  id: string
  kind: 'show_on_map' | 'open_calendar' | 'open_priorities' | 'open_report' | 'download_data'
  label: string
  country: string | null
  department: string | null
  year: number | null
  month: number | null
  report_id: string | null
}
export type AnalystStatus = { engine: 'deterministic' | 'claude'; model: string | null }
export type ReportCreated = {
  id: string
  headline: { kind: string; text: string }
  summary: string[]
  territory: { type: string; name: string; ubigeo: string | null; country: string; cells: number }
  validation_status: string
}
// Department priority table (POST /api/reports/priority): each indicator in its own column.
export type PriorityRow = {
  code: string
  name: string
  report_id: string
  month_value: number | null
  month_anomaly: number | null
  month_rank: number | null
  month_rank_of: number
  month_status: string
  season_rank: number | null
  season_rank_of: number | null
  season_anomaly: number | null
  trend_harmonized: number | null
  trend_harmonized_direction: string
  trend_raw: number | null
  significant_events: number | null
  emergencies: number | null
  forest_loss_ha: number | null
  forest_loss_with_fire_ha: number | null
  drought: boolean | null
}
export type PriorityTable = {
  dataset_id: string
  year: number
  month: number
  level: string
  generated_at: string
  rows: PriorityRow[]
  note: string
}
