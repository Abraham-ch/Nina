# NINA · Analytical assistant

The analytical assistant answers specialists' questions about a territory and a month using NINA's own data:
the harmonized record, the territorial report and its context layers, and the validation results. It states plainly
when a question is outside what those data can support. Code: `nina/analyst.py`; interface: `web/src/AnalystPanel.tsx`
(the "Explain" panel when the harmonized record is selected).

## 1. Endpoints

| Method | Route | Use |
|---|---|---|
| GET | `/api/analyst` | Active engine: `{"engine": "deterministic" \| "claude", "model": ...}` |
| POST | `/api/analyst` | Answer one question |

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
(`checked`, `unverified`, `passed`), `report_id` (to open the technical report), `dataset_id`, `validation_status` and
`notice` (set when the model could not give a verified answer and the deterministic one is shown).

## 2. Engines

| | Deterministic | Claude |
|---|---|---|
| Availability | Always; no network | When `ANTHROPIC_API_KEY` is set on the server |
| Question understanding | Keyword classifier (11 intents) and parser of place and period | The model plans the tool calls |
| Answer | Bilingual templates filled from tool results | Written by the model from tool results |
| Figures | From the tools | From the tools; checked before the answer is shown |
| Median latency (real data) | 0.49 s | Not yet measured |

Claude settings: model `claude-opus-5-5` (`NINA_ANALYST_MODEL`), effort `medium` (`NINA_ANALYST_EFFORT`), strict tool
schemas, at most ten model steps per question, prompt caching on the stable prefix, and server-side refusal fallback
(`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). The deterministic answer is returned, with a notice,
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

## 4. Figure verification

Every figure and ISO date in an answer must appear in a tool result of the same question (or in the question and the
on-screen period). The check:

- compares at the precision written; figures of 100 or more may be rounded within 0.5 % ("about 21,000" for 20,909.5);
- accepts fractions written as percentages (0.6585 → 65.9 %);
- ignores 0 and 1 and numbers that belong to names (`NOAA-20`, `H3`, `MCD64A1`, `v1.12`);
- admits derived figures only through `calculate`, whose operands must already be traced.

A model answer that fails gets one rewrite request naming the untraced figures; if it fails again the deterministic
answer is shown. The check proves where each number comes from; it does not prove that the reasoning around the numbers
is correct, which is why the system prompt also fixes the interpretation rules (unit, gaps, sensor change, events vs
emergencies, forest loss, climate as context).

## 5. Scope and abstention

NINA does not forecast fires or their spread, attribute causes, give operational instructions (evacuations, brigades,
resources), measure burned area, or report damage and casualties. Questions of these kinds are answered with the
reason and with what NINA can answer instead; no data tools are called. The model receives the same rules.

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
| Claude | — | — | pending (no key configured) | pending | pending | pending |

## 7. Configuration and privacy

```
ANTHROPIC_API_KEY=          # enables the Claude engine; keep it in .env locally or as a Fly.io secret
NINA_ANALYST_MODEL=claude-opus-5-5
NINA_ANALYST_EFFORT=medium
NINA_ANALYST_ENGINE=        # "deterministic" forces the offline engine
```

On Fly.io: `fly secrets set ANTHROPIC_API_KEY=...` (the key never goes into the repository or the image).

With the Claude engine, Anthropic receives the question, the name and period of the on-screen territory, up to six
previous turns and the tool results (aggregated statistics computed by NINA). It does not receive FIRMS or Earthdata
credentials, raw detections or user accounts. Each question is one conversation with a few tool calls, billed to the
key's account.

## 8. Known limits

- The deterministic classifier is keyword-based and gives one intent per question; the only combination it handles is
  a trend question that also asks about reliability (trend plus validation of the MODIS-era strata).
- Places recognised in the question: Peruvian departments, provinces with names of six letters or more,
  "district of X" / "distrito de X", and country names; otherwise the on-screen territory is used.
- The map draws Peruvian departments with geoBoundaries outlines; the report and the assistant resolve department
  names to INEI districts. Values can differ by a few percent (Ucayali, September 2024: 4,582 on the map, 4,491 in the
  report).
- `POST /api/harmonized/assistant` remains for compatibility; the web's harmonized "Explain" panel uses `/api/analyst`.
