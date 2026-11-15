# NINA · Analytical assistant

The analytical assistant answers specialists' questions about a territory and a month using NINA's own data:
the harmonized record, the territorial report and its context layers, and the validation results. It states plainly
when a question is outside what those data can support. Code: `nina/analyst.py`; interface: `web/src/AnalystPanel.tsx`
(the "Explain" panel when the harmonized record is selected).

**Architecture: an agent with tools, not RAG or GraphRAG.** NINA's answers are figures computed from tables (DuckDB
and Parquet). Retrieval by text similarity (RAG) or a graph of entities extracted from documents (GraphRAG) would hand
the model passages that look relevant and could mix years, territories or units, with no way to prove where a number
came from. Instead the model calls functions that query NINA's computed results, and a verifier checks every figure of
the answer against those results before it is shown (§4). The only document knowledge is a small set of curated
method notes selected by topic, not by similarity. Charts and tables are built by the server from the same results,
and official web sources are cited passage by passage.

## 1. Endpoints

| Method | Route | Use |
|---|---|---|
| GET | `/api/analyst` | Active engine: `{"engine": "deterministic" \| "claude", "model": ...}` |
| POST | `/api/analyst` | Answer one question |
| POST | `/api/analyst/stream` | The same answer preceded by live progress (server-sent events: `tool` start/done, `thinking`, `verifying`, `fallback`, then `answer` or `error`); the web panel shows each step as it happens |

Request:

```json
{
  "question": "Is the trend real or a sensor artefact?",
  "language": "en",
  "context": {"country": "Peru", "place_name": "Ucayali", "year": 2024, "month": 9},
  "history": []
}
```

`context` takes the same territory fields as a territorial report request (`country`, `ubigeo`, `geometry`,
`place_name`, `year`, `month`). `history` holds up to eight previous turns; it gives the model conversational context
but is never accepted as a source of figures.

The response carries `answer`, `engine`, `model`, `intent` (question type recognised by the classifier), `abstained`,
`facts` (key figures behind the answer), `tools` (calls made, with their arguments), `verification`
(`checked`, `unverified`, `passed`), `report_id` (to open the technical report), `dataset_id`, `validation_status`,
`notice` (set when the model could not give a verified answer and the deterministic one is shown), and:

- `visuals`: charts (`line`, `bar`) and tables built by the server from NINA's results, with title, unit, note and
  source. The model chooses what to show; it never types the numbers of a visual.
- `actions`: buttons the user can press (select a territory and period in the atlas, open the calendar or the
  department table, open the report, download its data package). The assistant never operates the interface itself.
- `follow_ups`: up to three questions NINA can answer next, by question type.
- `sources`: official web pages cited in the answer, each with the quoted passage (§3, web search).

## 2. Engines

| | Deterministic | Claude |
|---|---|---|
| Availability | Always; no network | When `ANTHROPIC_API_KEY` (or its alias `CLAUDE_API_KEY`) is set on the server |
| Question understanding | Keyword classifier (11 intents) and parser of place and period | The model plans the tool calls |
| Answer | Bilingual templates filled from tool results | Written by the model from tool results |
| Figures | From the tools | From the tools; checked before the answer is shown |
| Median latency (real data) | 1.1 s | 9.3 s (`claude-haiku-5-5`), 8.2 s (`claude-sonnet-5-5`) |
| Cost per question (median) | none | USD 0.0024 (Haiku 5.5); about 20 times more with Sonnet 5.5 |

Claude settings: model `claude-haiku-5-5` by default (`NINA_ANALYST_MODEL`; `claude-sonnet-5-5` also tested), effort
`medium` (`NINA_ANALYST_EFFORT`), strict tool schemas, at most ten model steps per question, prompt caching on the stable
prefix, and, for Sonnet, server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`;
Haiku 5.5 does not offer it). Text the model writes in the same turn as a chart or button request is kept as part of the
answer. The deterministic answer is returned, with a notice,
when the model refuses, runs out of tokens, cannot be reached, rejects the key, or produces figures that cannot be
traced even after one rewrite. `NINA_ANALYST_ENGINE=deterministic` keeps the assistant offline even with a key.

## 3. Tools

Both engines use the same registry; the deterministic engine calls the tools itself.

| Tool | Returns |
|---|---|
| `territory_profile` | Month against its normal (median, p10–p90, rank), Jul–Oct season, harmonized vs raw trend with annual totals, fire events vs INDECI emergencies, tree-cover loss, climate context, data quality, report id |
| `activity_series` | Monthly harmonized values of a territory, filtered by calendar month or years; `null` = no comparable value |
| `compare_departments` | Peru's departments for one month, each indicator separate, sorted by a chosen criterion (no composite score) |
| `validation_summary` | Validation gates, leave-one-year-out results of the MODIS calibration and the NOAA-20 bridge, per-biome strata of a country, transfer outside the calibration countries, static-source mask |
| `method_notes` | Documented definitions (unit, calibration, bridge, validation, gaps, events, emergencies, forest loss, climate, mask, limitations, sources) with their source documents |
| `find_territory` | Peruvian divisions (with UBIGEO) or a country by name |
| `calculate` | Arithmetic on figures already returned by other tools |
| `show_visual` | A chart or table under the answer: monthly series, same month across years with the median, harmonized vs raw annual index, events vs registered cases, forest loss, department ranking, validation strata of a country (with the NOAA-20 noise ceiling), climate by department. Returns the same numbers to the model |
| `propose_action` | A button: `show_on_map`, `open_calendar`, `open_priorities`, `open_report`, `download_data` |
| `web_search` (Claude engine only) | Anthropic's server-side web search, at most 3 searches per question, restricted to government, scientific and multilateral domains (`gob.pe`, `elperuano.pe`, `reliefweb.int`, `nasa.gov`, `fao.org`, `copernicus.eu`, `inpe.br`, `gov.br`, `nifc.gov`, `canada.ca`, `gob.mx`, `gob.bo`, `gov.au`, `bnpb.go.id`, `undrr.org`, `wmo.int`). Used to corroborate (declarations, official reports), never for figures NINA's tools provide. `NINA_ANALYST_WEB=false` turns it off |

The deterministic engine also attaches one chart or table per question type (for example the harmonized vs raw index
for a trend question) and detects requested actions ("open the calendar", "download the data"). Strict tool sets
accept at most 16 nullable parameters in total, so `show_visual` and `propose_action` use sentinels (`"current"`,
`0`, empty label) for the on-screen selection; `tests/test_analyst.py` guards the limit.

## 4. Figure verification

Every figure and ISO date in an answer must appear in a tool result of the same question (or in the question and the
on-screen period). The check:

- compares at the precision written; figures of 100 or more may be rounded within 0.5 % ("about 21,000" for 20,909.5);
- accepts fractions written as percentages (0.6585 → 65.9 %);
- ignores 0 and 1 and numbers that belong to names (`NOAA-20`, `H3`, `MCD64A1`, `v1.12`);
- admits derived figures only through `calculate`, whose operands must already be traced;
- admits a figure taken from the web only if it appears in the passage the answer cites.

A model answer that fails gets one rewrite request naming the untraced figures; if it fails again the deterministic
answer is shown. The check proves where each number comes from; it does not prove that the reasoning around the numbers
is correct, which is why the system prompt also fixes the interpretation rules (unit, gaps, sensor change, events vs
emergencies, forest loss, climate as context).

## 5. Scope and abstention

NINA does not forecast fires or their spread, attribute causes, give operational instructions (evacuations, brigades,
resources), measure burned area, or report damage and casualties. Questions of these kinds are answered with the
reason and with what NINA can answer instead; no data tools are called. The model receives the same rules, and when
the classifier recognises such a question the model is given only the method notes, so it cannot place figures next
to a forecast or cause question.

## 6. Evaluation

`docs/reference/analyst_eval.json` holds 31 questions in English and Spanish: 23 answerable (overview, trend, events,
forest, climate, quality, season, validation, comparison, method) and 8 out of scope. `tests/test_analyst.py` checks
the classifier on every item, the deterministic answers and their verification on a synthetic dataset, abstention, the
verifier against invented figures, `calculate`, and the model loop with a scripted client (rewrite and fallback).

`scripts/eval_analyst.py` runs the set against the configured dataset and writes
`data/reports/analyst_eval_<engine>_<timestamp>.json` with every answer.

| Engine | Date | Dataset | Figures traced | Correct abstention | Expected tools | Median time |
|---|---|---|---|---|---|---|
| Deterministic | 2026-11-15 | `e9f9a7a7a47bd640f9d27999` | 31 / 31 | 31 / 31 | 31 / 31 | 0.49 s |
| Claude (`claude-sonnet-5-5`) | 2026-11-15 | `e9f9a7a7a47bd640f9d27999` | 31 / 31 | 31 / 31* | 31 / 31* | 7.0 s |
| Deterministic, with charts and actions | 2026-11-15 | `e9f9a7a7a47bd640f9d27999` | 31 / 31 | 31 / 31 | 31 / 31 | 1.1 s |
| Claude Sonnet 5.5, with charts, actions and web search | 2026-11-15 | `e9f9a7a7a47bd640f9d27999` | 31 / 31 | 31 / 31 | 31 / 31 | 8.2 s |
| Claude Haiku 5.5 (default), same tools | 2026-11-15 | `e9f9a7a7a47bd640f9d27999` | 31 / 31† | 31 / 31 | 31 / 31 | 9.3 s |

† One answer fell back to the deterministic engine: the model's draft kept an untraced figure after the rewrite, so the
verified deterministic answer was shown. Haiku run: USD 0.076 for the 31 questions (median USD 0.0024 per question,
list prices). The Sonnet run showed 2 of 31 answers reduced to one sentence about the chart (the answer had been written
before the chart request and was dropped); that is fixed, and the evaluation now also requires a substantive answer
(at least 250 characters) for answerable questions.

Live checks with charts, actions and web corroboration (2026-11-15, Claude engine, all figures traced):

| Question | Tools | Visual | Action / sources |
|---|---|---|---|
| Was September 2024 unusual in Madre de Dios? Show how it compares | profile, show_visual | September of every year (bars, median) | — |
| Is the trend real or a sensor artefact? Show it and give me the report to download | profile, validation, show_visual, propose_action | harmonized vs raw index | download package |
| How reliable is the MODIS calibration in Brazil? Show the strata | validation, show_visual | strata table | — |
| Take me to Ucayali on the map in September 2024 and tell me which departments stand out | compare, propose_action | department table | show Ucayali in the atlas |
| Was an emergency declared in Amazonas in September 2024? Corroborate with official sources | web_search, profile | events vs emergencies | DS 097-2024-PCM (SINIA/MINAM), Radio Nacional, Informe Defensorial 225 |

\* The full run gave 30 / 31 on both: "What can NINA not answer?" was answered from the instructions without calling
`method_notes`. The instructions now require the method notes for method and limits questions; the three method
items were rerun and all called the tool. Two earlier runs led to the out-of-scope guard described in §5 (the model
had added historical figures after declining a forecast question). Reports: `data/reports/analyst_eval_*.json`.

## 7. Configuration and privacy

```
ANTHROPIC_API_KEY=          # enables the Claude engine; keep it in .env locally or as a Fly.io secret
NINA_ANALYST_MODEL=claude-haiku-5-5   # or claude-sonnet-5-5
NINA_ANALYST_EFFORT=medium
NINA_ANALYST_ENGINE=        # "deterministic" forces the offline engine
NINA_ANALYST_WEB=true       # "false" removes the web search tool
```

On Fly.io: `fly secrets set ANTHROPIC_API_KEY=...` (the key never goes into the repository or the image).

With the Claude engine, Anthropic receives the question, the name and period of the on-screen territory, up to six
previous turns and the tool results (aggregated statistics computed by NINA). It does not receive FIRMS or Earthdata
credentials, raw detections or user accounts. Each question is one conversation with a few tool calls, billed to the
key's account. Web search, when the model uses it, costs USD 10 per 1,000 searches plus tokens; the search queries are
written by the model from the question.

## 8. Known limits

- The deterministic classifier is keyword-based and gives one intent per question; the only combination it handles is
  a trend question that also asks about reliability (trend plus validation of the MODIS-era strata).
- Places recognised in the question: Peruvian departments, provinces with names of six letters or more,
  "district of X" / "distrito de X", and country names; otherwise the on-screen territory is used.
- The map draws Peruvian departments with geoBoundaries outlines; the report and the assistant resolve department
  names to INEI districts. Values can differ by a few percent (Ucayali, September 2024: 4,582 on the map, 4,491 in the
  report).
- `POST /api/harmonized/assistant` remains for compatibility; the web's harmonized "Explain" panel uses `/api/analyst`.
