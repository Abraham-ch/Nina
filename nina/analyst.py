"""Analytical assistant over the harmonized record and its territorial context layers.

One tool registry serves two engines:

* ``deterministic`` (always available): recognises the intent, territory and period of the question,
  calls the tools itself and answers from bilingual templates;
* ``claude`` (when ``ANTHROPIC_API_KEY`` or ``CLAUDE_API_KEY`` is set): Claude plans the tool calls and
  writes the answer.

Every figure in an answer must appear in a tool result of the same question. A model draft that fails
this check gets one rewrite; if it still fails, the deterministic answer is returned with a notice.
The assistant explains detected activity: it does not forecast fires, attribute causes, estimate
damage or give operational instructions, and it says so when asked.
"""

from __future__ import annotations

import ast
import contextvars
import json
import queue
import threading
import operator
import os
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import analyst_ui, harmonized, reports
from .analyst_ui import ACTION_KINDS, VISUAL_KINDS, AnalystAction, AnalystVisual
from .harmonized import load_json, published
from .report_document import format_number
from .reports import MONTH_NAMES, SIGNIFICANCE, PriorityRequest, ReportRequest, build_report, districts

router = APIRouter()
# Live progress of one question (tool calls, model turns, verification), read by /api/analyst/stream.
PROGRESS: contextvars.ContextVar[Callable[[dict[str, Any]], None] | None] = contextvars.ContextVar("PROGRESS",
                                                                                                  default=None)


def progress(event: dict[str, Any]) -> None:
    emit = PROGRESS.get()
    if emit is not None:
        emit(event)

DEFAULT_MODEL = "claude-haiku-5-5"  # 31/31 on the evaluation at about 1/20 of the Sonnet 5.5 cost per question
MAX_MODEL_STEPS = 10
FREE_NUMBERS = {0.0, 1.0}  # "one of", "zero" and list markers never need a source
CALCULATE_CONSTANTS = {100.0, 1000.0}  # allowed in derived figures (percentages, thousands)
UNIT_TEXT = "VIIRS S-NPP-equivalent active cell-days (H3 resolution 7, about 5 km²)"
P_FLOOR = 0.001  # smaller p-values are written as "p < 0.001"


# ---------------------------------------------------------------- request and response


class AnalystContext(BaseModel):
    """Territory and period on the user's screen (the body of a territorial report request)."""

    model_config = ConfigDict(extra="ignore")
    country: str = Field(default="Peru", max_length=100)
    ubigeo: str | None = Field(default=None, pattern=r"^\d{2}(\d{2}(\d{2})?)?$")
    geometry: dict | None = None
    place_name: str | None = Field(default=None, max_length=120)
    year: int = Field(ge=2002, le=2100)
    month: int = Field(ge=1, le=12)


class AnalystTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AnalystQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=600)
    language: Literal["en", "es"] = "en"
    context: AnalystContext
    history: list[AnalystTurn] = Field(default_factory=list, max_length=8)


class AnalystFact(BaseModel):
    label: str
    value: str
    tool: str


class AnalystSource(BaseModel):
    title: str
    url: str
    cited_text: str = Field(description="Passage of the page the answer relies on (up to 150 characters)")


class AnalystToolCall(BaseModel):
    name: str
    input: dict[str, Any]
    ok: bool


class AnalystVerification(BaseModel):
    checked: int = Field(description="Figures and dates found in the answer")
    unverified: list[str] = Field(description="Figures that no tool result of this question contains")
    passed: bool


class AnalystAnswer(BaseModel):
    answer: str
    engine: Literal["deterministic", "claude"]
    model: str | None = None
    intent: str = Field(description="Question type recognised by the deterministic classifier")
    abstained: bool = Field(description="True when the question is outside what NINA can answer")
    facts: list[AnalystFact]
    tools: list[AnalystToolCall]
    verification: AnalystVerification
    report_id: str | None = None
    dataset_id: str
    validation_status: Literal["validated", "experimental"]
    notice: str | None = None
    visuals: list[AnalystVisual] = Field(default_factory=list,
                                         description="Charts and tables built from NINA's results, never typed by the model")
    actions: list[AnalystAction] = Field(default_factory=list, description="Interface actions offered as buttons")
    follow_ups: list[str] = Field(default_factory=list, description="Questions NINA can answer next")
    sources: list[AnalystSource] = Field(default_factory=list,
                                         description="Official web sources cited in the answer (web search)")


class AnalystStatus(BaseModel):
    engine: Literal["deterministic", "claude"]
    model: str | None = None


# ---------------------------------------------------------------- places


def fold(text: str | None) -> str:
    """Upper-case ASCII without punctuation: 'Junín?' -> 'JUNIN'."""
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w\s'-]", " ", plain.upper()).split())


@lru_cache(maxsize=4)
def _divisions(path: str, stamp: int) -> tuple[dict[str, str], ...]:
    rows: dict[str, dict[str, str]] = {}
    for p, _ in districts():
        code = p["ubigeo"]
        department, province = reports.display_name(p["department"]), reports.display_name(p["province"])
        rows.setdefault(code[:2], {"ubigeo": code[:2], "level": "department", "name": department,
                                   "key": fold(p["department"])})
        rows.setdefault(code[:4], {"ubigeo": code[:4], "level": "province", "name": f"{province} ({department})",
                                   "key": fold(p["province"])})
        rows[code] = {"ubigeo": code, "level": "district", "key": fold(p["district"]),
                      "name": f"{reports.display_name(p['district'])} ({province}, {department})"}
    return tuple(rows.values())


def divisions() -> tuple[dict[str, str], ...]:
    path = reports.CONTEXT / "districts/peru_districts.geojson"
    return _divisions(str(path), path.stat().st_mtime_ns) if path.exists() else ()


LEVEL_ORDER = {"department": 0, "province": 1, "district": 2}
DIVISION_PREFIXES = ("REGION ", "DEPARTAMENTO DE ", "DEPARTMENT OF ", "PROVINCIA DE ", "PROVINCE OF ",
                     "DISTRITO DE ", "DISTRICT OF ")


def division_key(name: str) -> str:
    key = fold(name)
    for prefix in DIVISION_PREFIXES:
        key = key.removeprefix(prefix)
    return key


def find_divisions(name: str, limit: int = 8) -> list[dict[str, str]]:
    key = division_key(name)
    if not key:
        return []
    rows = divisions()
    exact = sorted((r for r in rows if r["key"] == key), key=lambda r: LEVEL_ORDER[r["level"]])
    partial = []
    if len(key) >= 4:
        partial = sorted((r for r in rows if r["key"] != key and key in r["key"]),
                         key=lambda r: (LEVEL_ORDER[r["level"]], r["name"]))
    return (exact + partial)[:limit]


COUNTRY_ALIASES = {
    "PERU": "Peru", "BRASIL": "Brazil", "ESTADOS UNIDOS": "United States of America",
    "EEUU": "United States of America", "USA": "United States of America", "UNITED STATES": "United States of America",
    "MEXICO": "Mexico", "ESPANA": "Spain", "CANADA": "Canada", "PANAMA": "Panama",
    "RUSIA": "Russia", "RUSSIAN FEDERATION": "Russia", "CONGO DR": "Dem. Rep. Congo", "RD CONGO": "Dem. Rep. Congo",
    "REPUBLICA DEMOCRATICA DEL CONGO": "Dem. Rep. Congo", "DEMOCRATIC REPUBLIC OF THE CONGO": "Dem. Rep. Congo",
    "SUDAFRICA": "South Africa", "GRECIA": "Greece", "TURQUIA": "Turkey", "TURKIYE": "Turkey",
    "KAZAJISTAN": "Kazakhstan", "KAZAJSTAN": "Kazakhstan", "ETIOPIA": "Ethiopia", "BIRMANIA": "Myanmar",
    "INDONESIA": "Indonesia", "AUSTRALIA": "Australia",
}


@lru_cache(maxsize=4)
def _country_names(path: str, stamp: int) -> dict[str, str]:
    names = {fold(f["properties"]["name"]): f["properties"]["name"] for f in load_json(Path(path))["features"]}
    for alias, name in COUNTRY_ALIASES.items():
        if fold(name) in names:
            names.setdefault(alias, name)
    return names


def country_names() -> dict[str, str]:
    path = harmonized.ROOT / "web/public/assets/countries.geojson"
    return _country_names(str(path), path.stat().st_mtime_ns) if path.exists() else {"PERU": "Peru"}


def find_country(text: str | None) -> str | None:
    return country_names().get(fold(text))


CURRENT_PLACE = {"", "CURRENT", "ACTUAL", "SELECTION", "SELECCION", "ON SCREEN", "HERE", "AQUI", "THIS AREA"}


def place_request(place: str | None, context: AnalystContext) -> dict[str, Any]:
    """Territory fields of a report request for a place argument ('current' = the on-screen selection)."""
    if fold(place) in CURRENT_PLACE:
        fields = {"country": context.country, "ubigeo": context.ubigeo, "geometry": context.geometry,
                  "place_name": context.place_name}
    else:
        text = (place or "").strip()
        if re.fullmatch(r"\d{2}(\d{2}(\d{2})?)?", text):
            fields = {"country": "Peru", "ubigeo": text}
        else:
            exact = [m for m in find_divisions(text, 3) if m["key"] == division_key(text)]
            country = find_country(text)
            if exact:
                fields = {"country": "Peru", "ubigeo": exact[0]["ubigeo"]}
            elif country:
                fields = {"country": country}
            else:
                hints = ", ".join(f"{m['name']} [{m['ubigeo']}]" for m in find_divisions(text, 5))
                raise ValueError(f"Unknown place '{place}'." + (f" Candidates: {hints}." if hints else "")
                                 + " Use find_territory, a UBIGEO code, a country name or 'current'.")
    if fields["country"] == "world" and not fields.get("geometry") and not fields.get("ubigeo"):
        raise ValueError("The whole planet has no territorial profile: choose a country, a Peruvian division "
                         "or a drawn area.")
    return fields


def context_label(context: AnalystContext, language: str = "en") -> str:
    """Readable name of the on-screen territory."""
    words = {"en": {"department": "department", "province": "province", "district": "district",
                    "area": "drawn area", "world": "the whole world"},
             "es": {"department": "departamento", "province": "provincia", "district": "distrito",
                    "area": "área dibujada", "world": "todo el mundo"}}[language]
    code = context.ubigeo or (reports.department_code(context.place_name) if context.country == "Peru" else None)
    if code:
        match = next((d for d in divisions() if d["ubigeo"] == code), None)
        if match:
            return f"{match['name']} ({words[match['level']]}, UBIGEO {code})"
    if context.place_name:
        return context.place_name
    if context.geometry:
        return f"{words['area']} ({context.country})" if context.country != "world" else words["area"]
    return words["world"] if context.country == "world" else context.country


# ---------------------------------------------------------------- figures and verification

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A figure: not glued to a word ('H3', 'NOAA-20', 'v1.12', 'MCD64A1') nor to a preceding decimal point.
NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")


def numbers_in(text: str) -> list[tuple[float, int, str]]:
    """(value, decimals, raw text) of every figure; ISO dates are checked separately."""
    found = []
    for match in NUMBER.finditer(ISO_DATE.sub(" ", text)):
        raw = match.group()
        digits = raw.replace(",", "")
        found.append((float(digits), len(digits.split(".")[1]) if "." in digits else 0, raw))
    return found


def collect(value: Any, numbers: list[float], texts: list[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.append(float(value))
    elif isinstance(value, str):
        texts.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            collect(item, numbers, texts)
    elif isinstance(value, (list, tuple)):
        for item in value:
            collect(item, numbers, texts)


def matches(value: float, decimals: int, known: list[float]) -> bool:
    """Equal at the precision written; figures of 100 or more may also be rounded (about 0.5 %)."""
    tolerance = 0.5 * 10 ** -decimals + 1e-9
    for candidate in known:
        distance = abs(abs(candidate) - value)
        if distance <= tolerance or (value >= 100 and distance <= 0.005 * abs(candidate)):
            return True
    return False


OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
             ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluate(expression: str) -> tuple[float, list[float]]:
    """Arithmetic only (+ - * / and parentheses); returns the result and the operands used."""
    if len(expression) > 200:
        raise ValueError("Expression too long")
    operands: list[float] = []

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            operands.append(float(node.value))
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.operand))
        raise ValueError("Only numbers, + - * / and parentheses are allowed")

    return walk(ast.parse(expression.replace(",", ""), mode="eval")), operands


# ---------------------------------------------------------------- session


class ToolFailed(Exception):
    pass


class Session:
    """The tool calls of one question. Every output is kept: the answer is checked against them."""

    def __init__(self, request: AnalystQuestion, report_cache: dict[str, dict] | None = None):
        self.request = request
        self.calls: list[dict[str, Any]] = []
        self.reports = report_cache if report_cache is not None else {}
        self.report_id: str | None = None
        self.visuals: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.sources: list[dict[str, str]] = []
        self.usage: dict[str, int] = {}  # tokens billed for this question (Claude engine)

    def period(self, year: int | None, month: int | None) -> tuple[int, int]:
        context = self.request.context
        year = context.year if year is None else int(year)
        month = context.month if month is None else int(month)
        if not 2002 <= year <= date.today().year:
            raise ValueError(f"year must be between 2002 and {date.today().year}")
        if not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        return year, month

    def report(self, place: str | None, year: int | None, month: int | None) -> dict[str, Any]:
        year, month = self.period(year, month)
        request = ReportRequest(**place_request(place, self.request.context), year=year, month=month,
                                language=self.request.language)
        key = request.model_dump_json()
        if key not in self.reports:
            self.reports[key] = build_report(request)
        report = self.reports[key]
        self.report_id = self.report_id or report["id"]
        return report

    def run(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = TOOLS.get(name)
        progress({"type": "tool", "name": name, "state": "start"})
        try:
            if tool is None:
                raise ValueError(f"Unknown tool '{name}'")
            output = tool.run(self, **arguments)
        except HTTPException as error:
            output = {"error": str(error.detail)}
        except (TypeError, ValueError, ZeroDivisionError, SyntaxError) as error:
            output = {"error": str(error)}
        self.calls.append({"name": name, "input": arguments, "ok": "error" not in output, "output": output})
        progress({"type": "tool", "name": name, "state": "done", "ok": "error" not in output})
        return output

    def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        output = self.run(name, arguments)
        if "error" in output:
            raise ToolFailed(output["error"])
        return output

    def known(self) -> tuple[list[float], str]:
        numbers: list[float] = []
        texts = [self.request.question]
        context = self.request.context
        numbers += [float(context.year), float(context.month)]
        for call in self.calls:
            if call["ok"]:
                collect(call["output"], numbers, texts)
        texts += [source["cited_text"] for source in self.sources]  # web figures must be in the cited passage
        for text in texts:
            numbers += [value for value, _, _ in numbers_in(text)]
        numbers += [value * 100 for value in numbers if abs(value) <= 1.5]  # fractions written as percentages
        return numbers, " ".join(texts)

    def verify(self, text: str) -> tuple[int, list[str]]:
        known, known_text = self.known()
        dates = ISO_DATE.findall(text)
        unverified = [d for d in dates if d not in known_text]
        figures = numbers_in(text)
        for value, decimals, raw in figures:
            if value not in FREE_NUMBERS and not matches(value, decimals, known):
                unverified.append(raw)
        return len(figures) + len(dates), unverified


# ---------------------------------------------------------------- tools


def nullable(kind: str, description: str, **extra: Any) -> dict[str, Any]:
    return {"anyOf": [{"type": kind, **extra}, {"type": "null"}], "description": description}


def rounded(value: Any, digits: int = 1) -> Any:
    return round(value, digits) if isinstance(value, float) else value


def pct(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(100 * value, digits)


def compact_events(events: dict[str, Any]) -> dict[str, Any]:
    if events["status"] != "available":
        return {"status": events["status"], "reason": events.get("reason")}
    return {"status": "available", "rule": events["rule"], "emergencies_source": events["emergencies_source"],
            "emergencies_coverage": events["emergencies_coverage"], "selected_year": events["selected_year"],
            "by_year": events["by_year"], "top_subdivisions": events["top_subdivisions"][:8],
            "validation_against_registry": events.get("validation")}


def compact_burned(burned: dict[str, Any]) -> dict[str, Any]:
    if burned.get("status") != "available":
        return {"status": burned.get("status", "not_available"), "reason": burned.get("reason")}
    return {"status": "available", "source": burned["source"], "note": burned["note"], "scope": burned["scope"],
            "unit": burned["unit"], "coverage": burned["coverage"],
            "selected_month": {k: rounded(v, 0) for k, v in burned["selected_month"].items()}
            if burned.get("selected_month") else None,
            "selected_year": {"year": burned["selected_year"]["year"],
                              "burned_ha": rounded(burned["selected_year"]["burned_ha"], 0),
                              "by_class": {k: rounded(v, 0) for k, v in burned["selected_year"]["by_class"].items()}}
            if burned.get("selected_year") else None,
            "by_year": [{"year": r["year"], "burned_ha": rounded(r["burned_ha"], 0)} for r in burned["by_year"]]}


def compact_forest(forest: dict[str, Any]) -> dict[str, Any]:
    if forest["status"] != "available":
        return {"status": forest["status"], "reason": forest.get("reason")}
    rows = [{k: rounded(v, 0) for k, v in row.items()} for row in forest["by_year"]]
    selected = forest["selected_year"]
    return {"status": "available", "definition": forest["definition"], "caveats": forest["caveats"],
            "validation": forest["validation"], "source_version": forest["source_version"],
            "cross_check": forest.get("cross_check"),
            "forest_2000_ha": rounded(forest["forest_2000_ha"], 0),
            "selected_year": {k: rounded(v, 0) for k, v in selected.items()} if selected else None,
            "last_year_available": forest["last_year_available"], "by_year": rows}


def compact_climate(climate: dict[str, Any]) -> dict[str, Any]:
    if climate["status"] != "available":
        return {"status": climate["status"], "reason": climate.get("reason")}
    selected = [{k: rounded(v, 2) for k, v in row.items()} for row in climate["selected_month"]]
    applicable = [row for row in selected if row["drought"] is not None]
    return {"status": "available", "source": climate["source"], "note": climate["note"],
            "cross_check": climate.get("cross_check"),
            "selected_month": selected,
            "departments_with_drought": sum(bool(row["drought"]) for row in applicable),
            "departments_where_drought_applies": len(applicable),
            "season_jul_oct": [{k: rounded(v, 2) for k, v in row.items()} for row in climate["season_jul_oct"]]}


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    """The facts of a territorial report, rounded and without chart-only data."""
    s = report["sections"]
    month, history = s["current"]["month"], s["history"]
    mtd = s["current"]["month_to_date"]
    quality = s["quality"]
    trend_fields = ("slope_pct_per_year", "p_value", "direction")
    return {
        "territory": {k: report["territory"].get(k) for k in ("name", "type", "ubigeo", "country", "cells")},
        "period": report["period"],
        "unit": UNIT_TEXT,
        "validation_status": report["validation_status"],
        "headline": report["headline"]["text"],
        "summary": report["summary"],
        "month": {
            "value": rounded(month["value"]), "status": month["status"],
            "anomaly_percent": rounded(month["anomaly_percent"]),
            "historical_median": rounded(month["historical_median"]),
            "historical_p10": rounded(month.get("historical_p10")), "historical_p90": rounded(month.get("historical_p90")),
            "years_compared": month["historical_n"], "rank": month["rank"], "rank_of": month["rank_of"],
            "partial_coverage": month["partial_coverage"], "is_provisional": month["is_provisional"],
        },
        "month_to_date": None if not mtd else {
            k: rounded(mtd.get(k)) for k in ("through_day", "valid_days", "value", "historical_median",
                                              "historical_n", "anomaly_percent", "rank", "rank_of",
                                              "sampling_bias_warning")},
        "season_jul_oct": {k: rounded(v) for k, v in (history.get("season_jul_oct") or {}).items()},
        "trend": {
            "period": history["trend_period"],
            "method": "Theil-Sen slope as a percentage of the median per year; Mann-Kendall test; the current, "
            "incomplete year is excluded",
            "significance_level": SIGNIFICANCE,
            "p_value_floor": P_FLOOR,
            "harmonized": {k: history["trend_harmonized"][k] for k in trend_fields},
            "raw_pixels": {k: history["trend_raw_pixels"][k] for k in trend_fields},
        },
        "annual": [{"year": a["year"], "harmonized": rounded(a["harmonized"], 0), "raw_pixels": rounded(a["raw_pixels"], 0)}
                   for a in history["annual"]],
        "events": compact_events(s["events"]),
        "burned_area": compact_burned(s.get("burned_area") or {"status": "not_available"}),
        "forest": compact_forest(s["forest"]),
        "climate": compact_climate(s["climate"]),
        "quality": {k: rounded(quality[k], 3) for k in ("valid_region_days", "expected_region_days", "noaa20_filled_days",
                                                         "unvalidated_share", "is_provisional", "validation_status",
                                                         "typical_yearly_error")},
        "report_id": report["id"],
    }


def run_find_territory(session: Session, name: str) -> dict[str, Any]:
    found = find_divisions(name)
    country = find_country(name)
    if not found and not country:
        return {"error": f"No Peruvian department, province, district or country named '{name}'"}
    return {"divisions": [{k: m[k] for k in ("ubigeo", "level", "name")} for m in found], "country": country}


def run_territory_profile(session: Session, place: str | None, year: int | None, month: int | None) -> dict[str, Any]:
    return compact_report(session.report(place, year, month))


def run_activity_series(session: Session, place: str | None, month: int | None, year_start: int | None,
                        year_end: int | None) -> dict[str, Any]:
    if month is not None and not 1 <= int(month) <= 12:
        raise ValueError("month must be between 1 and 12")
    report = session.report(place, None, None)
    rows = [
        {"year": m["year"], "month": m["month"], "value": rounded(m["value"]), "status": m["status"],
         "anomaly_percent": rounded(m["anomaly_percent"])}
        for m in report["sections"]["current"]["calendar"]
        if (month is None or m["month"] == month) and (year_start is None or m["year"] >= year_start)
        and (year_end is None or m["year"] <= year_end)
    ]
    return {"territory": report["territory"]["name"], "unit": UNIT_TEXT, "months": len(rows), "rows": rows[-180:],
            "note": "value null = no comparable value (gap, partial or outside the validated domain), never zero"}


SORTS = {
    "month_anomaly": ("month_anomaly", False), "month_value": ("month_value", False),
    "season": ("season_rank", True), "trend": ("trend_harmonized", False),
    "events": ("significant_events", False), "emergencies": ("emergencies", False),
    "forest_loss": ("forest_loss_ha", False),
}
ROW_FIELDS = ("code", "name", "month_value", "month_anomaly", "month_rank", "month_rank_of", "month_status",
              "season_rank", "season_rank_of", "season_anomaly", "trend_harmonized", "trend_harmonized_direction",
              "trend_raw", "significant_events", "emergencies", "forest_loss_ha", "forest_loss_with_fire_ha", "drought")


def run_compare_departments(session: Session, year: int | None, month: int | None, sort_by: str | None,
                            limit: int | None) -> dict[str, Any]:
    year, month = session.period(year, month)
    sort_by = sort_by or "month_anomaly"
    if sort_by not in SORTS:
        raise ValueError(f"sort_by must be one of {sorted(SORTS)}")
    limit = max(1, min(25, 10 if limit is None else int(limit)))
    table = reports.priority(PriorityRequest(year=year, month=month, language=session.request.language))
    key, ascending = SORTS[sort_by]

    def order(row: dict[str, Any]) -> tuple:
        value = row[key]
        return (value is None, 0 if value is None else (value if ascending else -value), row["name"])

    rows = sorted(table["rows"], key=order)
    return {
        "year": year, "month": month, "level": "Peruvian departments", "sort_by": sort_by,
        "departments": len(rows),
        "rows": [{k: rounded(row[k]) for k in ROW_FIELDS} for row in rows[:limit]],
        "columns": {"month_value": UNIT_TEXT, "month_anomaly": "% against the median of the other years",
                    "trend_harmonized": "%/year, harmonized series", "trend_raw": "%/year, raw pixel counts",
                    "significant_events": "fire events with at least 5 active cell-days, in the year",
                    "emergencies": "INDECI forest-fire emergencies, in the year",
                    "forest_loss_ha": "Hansen/UMD tree-cover loss, hectares, in the year"},
        "note": table["note"],
    }


LINKS = (("terra_aqua", "MODIS Terra+Aqua to VIIRS S-NPP"), ("terra_only", "MODIS Terra only to VIIRS S-NPP (not served)"),
         ("noaa20", "VIIRS NOAA-20 to VIIRS S-NPP bridge"))
GATE_MEANING = {"static_mask": "static-source mask (recovery of reference static cells, vegetation removed)",
                "terra_only": "MODIS Terra-only calibration", "terra_aqua": "MODIS Terra+Aqua calibration",
                "noaa20": "NOAA-20 to S-NPP bridge"}
BIOMES = {
    "en": {0: "cells outside RESOLVE biomes, mostly coast and water edges", 1: "tropical and subtropical moist broadleaf forests",
           2: "tropical and subtropical dry broadleaf forests", 3: "tropical and subtropical coniferous forests",
           4: "temperate broadleaf and mixed forests", 5: "temperate conifer forests", 6: "boreal forests and taiga",
           7: "tropical and subtropical grasslands, savannas and shrublands",
           8: "temperate grasslands, savannas and shrublands", 9: "flooded grasslands and savannas",
           10: "montane grasslands and shrublands", 11: "tundra", 12: "Mediterranean forests, woodlands and scrub",
           13: "deserts and xeric shrublands", 14: "mangroves"},
    "es": {0: "celdas fuera de los biomas RESOLVE, sobre todo costa y bordes de agua", 1: "bosques húmedos tropicales y subtropicales",
           2: "bosques secos tropicales y subtropicales", 3: "bosques de coníferas tropicales y subtropicales",
           4: "bosques templados de hoja ancha y mixtos", 5: "bosques templados de coníferas", 6: "bosques boreales y taiga",
           7: "pastizales, sabanas y matorrales tropicales y subtropicales",
           8: "pastizales, sabanas y matorrales templados", 9: "pastizales y sabanas inundables",
           10: "pastizales y matorrales de montaña", 11: "tundra", 12: "bosques y matorrales mediterráneos",
           13: "desiertos y matorrales xéricos", 14: "manglares"},
}


def link_summary(block: dict[str, Any], label: str) -> dict[str, Any]:
    overall = block.get("overall") or {}
    per_year = block.get("per_year_error_in_passed_strata") or {}
    strata = block.get("strata") or []
    return {
        "link": label, "method": "leave-one-year-out cross-validation",
        "scope": "pooled over the evaluable country-biome strata of all calibration countries, not one country",
        "years": [block["years"][0], block["years"][-1]] if block.get("years") else None,
        "strata_evaluable": sum(bool(s.get("evaluable")) for s in strata),
        "strata_passing": sum(bool(s.get("passed")) for s in strata),
        "strata_passing_percent": pct(block.get("passed_fraction"), 2),
        "required_percent": pct(block.get("minimum_fraction"), 0),
        "max_abs_bias_percent": pct(block.get("max_absolute_bias"), 0),
        "min_spearman": block.get("minimum_spearman"),
        "gate_passed": bool(block.get("passed")),
        "aggregate_relative_bias_percent": pct(overall.get("relative_bias"), 2),
        "aggregate_spearman": rounded(overall.get("spearman"), 3),
        "aggregate_r2": rounded(overall.get("r2"), 3),
        "yearly_error_median_percent": pct(per_year.get("yearly_abs_bias_median"), 1),
        "yearly_error_p90_percent": pct(per_year.get("yearly_abs_bias_p90"), 1),
        "years_within_10_percent": pct(per_year.get("years_within_10pct"), 0),
    }


def run_validation_summary(session: Session, country: str | None) -> dict[str, Any]:
    manifest, _ = published()
    validation = manifest.get("validation") or {}
    context = session.request.context
    default = "Peru" if context.ubigeo or context.country == "world" else context.country
    country = find_country(country) or country or default
    output: dict[str, Any] = {
        "dataset_id": manifest["id"], "method_version": manifest.get("method_version"),
        "is_published": manifest.get("status") == "published",
        "status": "published (all gates passed)" if manifest.get("status") == "published"
        else "experimental candidate (not all validation gates passed)",
        "gates": manifest.get("gates"), "gate_meaning": GATE_MEANING,
        "cloud_free_opportunities": manifest.get("local_cloud_opportunities"),
        "static_mask": NOTES["static_mask"]["en"],
        "country": country,
        "context_layers": {
            "events_vs_registries": {name: (reports.validation_file(f) or {}).get("headline")
                                     for name, f in reports.EVENT_VALIDATIONS.items()
                                     if reports.validation_file(f)},
            "forest_vs_geobosques": (reports.validation_file("forest_peru_geobosques") or {}).get("headline"),
            "climate_vs_chirps": (reports.validation_file("climate_peru_chirps") or {}).get("headline"),
        },
    }
    if not validation:
        output["details"] = "this dataset manifest carries no per-stratum validation details"
        return output
    output["links"] = {key: link_summary(validation[key], label) for key, label in LINKS if key in validation}
    calibration = sorted({s["country"] for s in validation.get("terra_aqua", {}).get("strata", [])})
    output["calibration_countries"] = calibration
    output["country_is_calibration_country"] = country in calibration
    strata, counts = [], {}
    for key in ("terra_aqua", "noaa20"):
        rows = [s for s in validation.get(key, {}).get("strata", []) if s["country"] == country]
        counts[key] = {"evaluable": sum(bool(s["evaluable"]) for s in rows), "passed": sum(bool(s["passed"]) for s in rows)}
        strata += [{
            "link": key, "biome_code": s["biome"], "biome": BIOMES["en"].get(s["biome"], str(s["biome"])),
            "evaluable": bool(s["evaluable"]), "passed": bool(s["passed"]),
            "relative_bias_percent": pct(s.get("relative_bias"), 1), "spearman": rounded(s.get("spearman"), 2),
            "yearly_error_median_percent": pct(s.get("yearly_abs_bias_median"), 1),
            "years_within_10_percent": pct(s.get("years_within_10pct"), 0),
        } for s in rows]
    output["country_strata"] = strata
    output["country_strata_scope"] = f"strata of {country} only (one row per link and biome)"
    output["country_strata_counts"] = counts
    output["outside_calibration_countries_2026"] = {
        key: {"relative_bias_percent": pct(block["metrics"]["relative_bias"], 2),
              "raw_relative_bias_percent": pct(block["raw_baseline"]["relative_bias"], 2)}
        for key, block in (manifest.get("geographic_diagnostic") or {}).items()
        if block.get("metrics") and block.get("raw_baseline")
    }
    return output


NOTES: dict[str, dict[str, str]] = {
    "unit": {
        "source": "docs/HARMONIZED_CONTRACT.md; AGENTS.md section 10.1",
        "en": "The unit is one active H3 cell (resolution 7, about 5 km²) per day, on a VIIRS S-NPP-equivalent scale. "
        "A cell is active on a day when it has at least one valid detection. Counting active cells instead of pixels "
        "reduces the resolution difference between MODIS (1 km pixels) and VIIRS (375 m pixels) before calibration. "
        "A unit measures detected activity: it is not a fire, a burned area or a fire location.",
        "es": "La unidad es una celda H3 activa (resolución 7, unos 5 km²) por día, en escala equivalente a VIIRS S-NPP. "
        "Una celda está activa en un día cuando tiene al menos una detección válida. Contar celdas activas en lugar de "
        "píxeles reduce la diferencia de resolución entre MODIS (píxeles de 1 km) y VIIRS (píxeles de 375 m) antes de "
        "calibrar. Una unidad mide actividad detectada: no es un incendio, un área quemada ni la ubicación de un fuego.",
    },
    "calibration": {
        "source": "docs/adr/0002 to 0005; packages/nina/README.md",
        "en": "MODIS (Terra and Aqua combined) is converted to the VIIRS S-NPP scale with ratio-of-totals coefficients "
        "fitted per country, biome (RESOLVE 2017), calendar month and sampling regime over the overlap years. Each "
        "coefficient is evaluated with leave-one-year-out cross-validation: every year is predicted with coefficients "
        "trained without it. From 2012 the record uses observed VIIRS S-NPP; NOAA-20 fills days without S-NPP and "
        "continues the series through the NOAA-20 to S-NPP bridge. Raw MODIS and VIIRS counts are never added together.",
        "es": "MODIS (Terra y Aqua combinados) se convierte a la escala de VIIRS S-NPP con coeficientes de razón de totales "
        "ajustados por país, bioma (RESOLVE 2017), mes calendario y régimen de muestreo en los años de solapamiento. "
        "Cada coeficiente se evalúa con validación cruzada dejando un año fuera: cada año se predice con coeficientes "
        "entrenados sin él. Desde 2012 el registro usa VIIRS S-NPP observado; NOAA-20 completa los días sin S-NPP y "
        "continúa la serie mediante el puente NOAA-20 a S-NPP. Los conteos crudos de MODIS y VIIRS nunca se suman.",
    },
    "noaa20_bridge": {
        "source": "docs/BACKEND_STATUS.md; AGENTS.md section 5.3",
        "en": "NOAA-20 (data from April 2018) is converted to the S-NPP scale with the same kind of coefficients, fitted "
        "on the years both satellites observed. It fills days without S-NPP data and carries the series after S-NPP "
        "stopped delivering data on 2 November 2026. This bridge is the only link whose validation gate passes.",
        "es": "NOAA-20 (datos desde abril de 2018) se convierte a la escala de S-NPP con el mismo tipo de coeficientes, "
        "ajustados en los años observados por ambos satélites. Completa los días sin datos de S-NPP y continúa la serie "
        "desde que S-NPP dejó de entregar datos el 2 de noviembre de 2026. Este puente es el único enlace que supera su "
        "puerta de validación.",
    },
    "validation": {
        "source": "AGENTS.md section 10.3; docs/BACKEND_STATUS.md",
        "en": "Validation is leave-one-year-out: each year is predicted by coefficients trained on the other years. A link "
        "passes when at least 80 % of evaluable country-biome strata meet the limits on absolute relative bias (10 % "
        "for MODIS, 5 % for the NOAA-20 bridge) and Spearman correlation (0.8). A good aggregate is not enough: the "
        "per-stratum and per-year errors decide.",
        "es": "La validación deja un año fuera: cada año se predice con coeficientes entrenados en los demás. Un enlace "
        "aprueba cuando al menos el 80 % de los estratos país-bioma evaluables cumplen los límites de sesgo relativo "
        "absoluto (10 % para MODIS, 5 % para el puente NOAA-20) y de correlación de Spearman (0.8). Un buen agregado no "
        "basta: deciden los errores por estrato y por año.",
    },
    "gaps": {
        "source": "AGENTS.md sections 5.4 and 8",
        "en": "A day or month without data is a gap, never zero activity. Known MODIS outages and days without support "
        "are marked as gaps; months with gaps or partial coverage on more than 20 % of their days are excluded from the "
        "climatology and the rankings. Provisional near-real-time data stay marked until the standard product replaces "
        "them.",
        "es": "Un día o mes sin datos es un vacío, nunca actividad cero. Las interrupciones conocidas de MODIS y los días "
        "sin soporte se marcan como vacíos; los meses con vacíos o cobertura parcial en más del 20 % de sus días se "
        "excluyen de la climatología y de los rankings. Los datos provisionales casi en tiempo real quedan marcados "
        "hasta que el producto estándar los reemplaza.",
    },
    "events": {
        "source": "docs/TERRITORIAL_REPORT.md",
        "en": "A fire event joins active cell-days that touch each other (neighbouring H3 cells) with gaps of at most 2 "
        "days. A significant event has at least 5 active cell-days. Events are computed for the VIIRS era (from 2012) "
        "only. An event is a cluster of detected activity, not an official fire record.",
        "es": "Un evento de incendio une celdas-día activas que se tocan (celdas H3 vecinas) con vacíos de hasta 2 días. Un "
        "evento significativo tiene al menos 5 celdas-día activas. Los eventos se calculan solo para la era VIIRS (desde "
        "2012). Un evento es un conglomerado de actividad detectada, no un registro oficial de incendio.",
    },
    "emergencies": {
        "source": "docs/TERRITORIAL_REPORT.md; docs/DATA_SOURCES.md",
        "en": "INDECI/SINPAD forest-fire emergencies are official records of emergencies with damage assessment, by "
        "district (UBIGEO). They count registered emergencies, not every fire. NINA uses only their number, not their "
        "figures on people affected or damage.",
        "es": "Las emergencias por incendio forestal de INDECI/SINPAD son registros oficiales de emergencias con evaluación "
        "de daños, por distrito (UBIGEO). Cuentan emergencias registradas, no todo incendio. NINA usa solo su número, no "
        "sus cifras de personas afectadas ni de daños.",
    },
    "forest_loss": {
        "source": "docs/DATA_SOURCES.md; docs/TERRITORIAL_REPORT.md",
        "en": "Tree-cover loss comes from Hansen/UMD Global Forest Change (canopy of at least 30 % in 2000), aggregated to "
        "H3 cells. It is stand-replacing loss, not deforestation. 'With fire' means the cell had satellite fire activity "
        "in the same or the previous year: co-location, not causation. Hansen's method changed in 2011-2012, so trends "
        "are not read across that break.",
        "es": "La pérdida de cobertura arbórea proviene de Hansen/UMD Global Forest Change (dosel de al menos 30 % en 2000), "
        "agregada a celdas H3. Es pérdida que reemplaza el rodal, no deforestación. 'Con fuego' significa que la celda "
        "tuvo actividad de fuego satelital el mismo año o el anterior: coincidencia, no causalidad. El método de Hansen "
        "cambió en 2011-2012, por lo que no se leen tendencias a través de ese corte.",
    },
    "climate": {
        "source": "docs/DATA_SOURCES.md",
        "en": "Climate context is monthly by department, as anomalies against 2002-2024: rainfall from CHIRPS v2.0 "
        "(satellite and gauges, 0.05 degree) and vapour-pressure deficit from NASA POWER (MERRA-2 reanalysis, about 0.5 "
        "degree). NASA POWER rainfall was replaced because its anomalies agree only moderately with CHIRPS in Peru "
        "(median r 0.45). Drought means rainfall z of -1 or less with vapour-pressure deficit z of +1 or more; it does "
        "not apply in months with under 10 mm of normal rainfall. It is context only and does not attribute fire "
        "activity to the weather.",
        "es": "El contexto climático es mensual por departamento, como anomalías respecto de 2002-2024: lluvia de CHIRPS "
        "v2.0 (satélite y estaciones, 0.05 grados) y déficit de presión de vapor de NASA POWER (reanálisis MERRA-2, unos "
        "0.5 grados). La lluvia de NASA POWER se reemplazó porque sus anomalías concuerdan solo moderadamente con CHIRPS "
        "en el Perú (r mediano 0.45). Sequía significa z de lluvia de -1 o menos con z de déficit de presión de vapor de "
        "+1 o más; no aplica en meses con menos de 10 mm de lluvia normal. Es solo contexto y no atribuye la actividad "
        "de fuego al clima.",
    },
    "static_mask": {
        "source": "docs/BACKEND_STATUS.md",
        "en": "Static heat sources (gas flares, volcanoes, industry, urban heat) are removed with a mask: cells with "
        "detections on 16 or more days of the same year, GHSL urban centres, volcano surroundings and water. In method "
        "0.4.0 the mask recovers 43.72 % of reference static cells (10,943 of 25,032) and removes 1.18 % of vegetation "
        "rows; its gate requires at least 80 % recovery with at most 2 % removal, so it fails.",
        "es": "Las fuentes de calor estáticas (quema de gas, volcanes, industria, calor urbano) se eliminan con una máscara: "
        "celdas con detecciones en 16 o más días del mismo año, centros urbanos GHSL, entornos de volcanes y agua. En el "
        "método 0.4.0 la máscara recupera el 43.72 % de las celdas estáticas de referencia (10,943 de 25,032) y elimina "
        "el 1.18 % de las filas de vegetación; su puerta exige al menos 80 % de recuperación con un máximo de 2 % "
        "eliminado, por lo que no aprueba.",
    },
    "limitations": {
        "source": "docs/PROBLEM.md; AGENTS.md section 11",
        "en": "NINA describes fire activity detected by satellites. It does not forecast fires or their spread, attribute "
        "causes, measure burned area or damage, or replace field verification. FIRMS does not recommend these data for "
        "tactical or local-scale decisions. Cloud-free observation opportunities are not reconstructed, so a low value "
        "can reflect clouds. The harmonized record is an experimental candidate: only the NOAA-20 bridge gate passes.",
        "es": "NINA describe la actividad de fuego detectada por satélites. No pronostica incendios ni su propagación, no "
        "atribuye causas, no mide área quemada ni daños y no reemplaza la verificación en campo. FIRMS no recomienda "
        "estos datos para decisiones tácticas o de escala local. Las oportunidades de observación sin nubes no se "
        "reconstruyen, por lo que un valor bajo puede deberse a nubes. El registro armonizado es un candidato "
        "experimental: solo aprueba la puerta del puente NOAA-20.",
    },
    "sources": {
        "source": "docs/DATA_SOURCES.md",
        "en": "Sources: NASA FIRMS active fires (MODIS Collection 6.1; VIIRS 375 m Collection 2 from S-NPP, NOAA-20 and "
        "NOAA-21), INEI/MINAM district boundaries, INDECI/SINPAD forest-fire emergencies, Hansen/UMD Global Forest "
        "Change, NASA POWER climate, RESOLVE Ecoregions 2017, GHSL urban centres and NASA GIBS imagery.",
        "es": "Fuentes: incendios activos de NASA FIRMS (MODIS Colección 6.1; VIIRS 375 m Colección 2 de S-NPP, NOAA-20 y "
        "NOAA-21), límites distritales de INEI/MINAM, emergencias por incendio forestal de INDECI/SINPAD, Hansen/UMD "
        "Global Forest Change, clima de NASA POWER, Ecorregiones RESOLVE 2017, centros urbanos GHSL e imágenes de NASA GIBS.",
    },
}


def run_method_notes(session: Session, topic: str) -> dict[str, Any]:
    if topic not in NOTES:
        raise ValueError(f"topic must be one of {sorted(NOTES)}")
    note = NOTES[topic]
    return {"topic": topic, "text": note[session.request.language], "source": note["source"]}


def run_calculate(session: Session, expression: str) -> dict[str, Any]:
    value, operands = evaluate(expression)
    known, _ = session.known()
    unknown = [o for o in operands if o not in CALCULATE_CONSTANTS and not matches(o, 4, known)]
    if unknown:
        return {"error": f"Operands not found in earlier tool results: {unknown}. Call a data tool first."}
    return {"expression": expression, "result": round(value, 4)}


MAX_VISUALS = 3
MAX_ACTIONS = 3
# Strict tools allow at most 16 nullable (union) parameters in total, so the interface tools use sentinels:
# place "current" and year/month 0 mean the on-screen selection, an empty label means the default text.
PLAIN_PLACE = {"type": "string", "description": "Territory as in territory_profile (for validation_strata, a "
               "country); 'current' = the on-screen selection."}
PLAIN_YEAR = {"type": "integer", "description": "Year; 0 = the on-screen year."}
PLAIN_MONTH = {"type": "integer", "description": "Calendar month 1-12; 0 = the on-screen month."}


def unset(value: Any) -> Any:
    """Sentinel values of the interface tools mean 'the on-screen selection'."""
    return None if value in (0, "", None) else value


def ordered_departments(rows: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    key, ascending = SORTS[sort_by]

    def order(row: dict[str, Any]) -> tuple:
        value = row[key]
        return (value is None, 0 if value is None else (value if ascending else -value), row["name"])

    return sorted(rows, key=order)


def run_show_visual(session: Session, kind: str, place: str | None, year: int | None,
                    month: int | None) -> dict[str, Any]:
    if kind not in VISUAL_KINDS:
        raise ValueError(f"kind must be one of {sorted(VISUAL_KINDS)}")
    if len(session.visuals) >= MAX_VISUALS:
        return {"error": f"At most {MAX_VISUALS} charts or tables per answer; refer to the ones already shown."}
    place, year, month = unset(place), unset(year), unset(month)
    language = session.request.language
    identifier = f"v{len(session.visuals) + 1}"
    if kind == "department_ranking":
        year, month = session.period(year, month)
        table = reports.priority(PriorityRequest(year=year, month=month, language=language))
        spec = analyst_ui.department_ranking(identifier, table, ordered_departments(table["rows"], "month_anomaly"),
                                             language, year, month)
    elif kind == "validation_strata":
        manifest, _ = published()
        context = session.request.context
        default = "Peru" if context.ubigeo or context.country == "world" else context.country
        country = find_country(place) or (default if fold(place) in CURRENT_PLACE else place) or default
        spec = analyst_ui.validation_strata(identifier, manifest.get("validation") or {}, str(country),
                                            BIOMES[language], language)
        if spec is None:
            return {"error": f"No validation strata for '{country}': it is not a calibration country."}
    else:
        builder = {"monthly_series": analyst_ui.monthly_series, "same_month_by_year": analyst_ui.same_month_by_year,
                   "annual_totals": analyst_ui.annual_totals, "events_by_year": analyst_ui.events_by_year,
                   "forest_loss_by_year": analyst_ui.forest_loss_by_year,
                   "burned_area_by_year": analyst_ui.burned_area_by_year,
                   "climate_departments": analyst_ui.climate_departments}[kind]
        spec = builder(identifier, session.report(place, year, month), language)
        if spec is None:
            return {"error": f"'{kind}' is not available for this territory (the layer does not cover it)."}
    session.visuals.append(spec)
    return analyst_ui.compact(spec)


ACTION_LABELS = {
    "en": {"show_on_map": "Show {place} in the atlas", "open_calendar": "Open the calendar of {place}",
           "open_priorities": "Open the department table for {period}", "open_report": "Open the report of {place}",
           "download_data": "Download the data of {place}"},
    "es": {"show_on_map": "Ver {place} en el atlas", "open_calendar": "Abrir el calendario de {place}",
           "open_priorities": "Abrir la tabla de departamentos de {period}", "open_report": "Abrir el informe de {place}",
           "download_data": "Descargar los datos de {place}"},
}


def run_propose_action(session: Session, action: str, place: str | None, year: int | None, month: int | None,
                       label: str | None) -> dict[str, Any]:
    if action not in ACTION_KINDS:
        raise ValueError(f"action must be one of {sorted(ACTION_KINDS)}")
    if len(session.actions) >= MAX_ACTIONS:
        return {"error": f"At most {MAX_ACTIONS} actions per answer."}
    place, year, month, label = unset(place), unset(year), unset(month), unset(label)
    language = session.request.language
    year, month = session.period(year, month)
    country, department, report_id = "Peru", None, None
    if action != "open_priorities":
        fields = place_request(place, session.request.context)
        country = fields["country"]
        code = fields.get("ubigeo") or (reports.department_code(fields.get("place_name")) if country == "Peru" else None)
        if code:
            match = next((d for d in divisions() if d["ubigeo"] == code[:2]), None)
            department = match["name"] if match else None
        if action in {"show_on_map", "open_calendar"} and country == "world":
            raise ValueError("A drawn area cannot be selected again from here; offer open_report instead.")
        if action in {"open_report", "download_data"}:
            report_id = session.report(place, year, month)["id"]
    name = department or (country if action != "open_priorities" else "Peru")
    period = f"{MONTH_NAMES[language][month - 1]} {year}"
    text = (label or "").strip()[:80] or ACTION_LABELS[language][action].format(place=name, period=period)
    spec = AnalystAction(id=f"a{len(session.actions) + 1}", kind=action, label=text, country=country,
                         department=department, year=year, month=month, report_id=report_id).model_dump()
    session.actions.append(spec)
    note = ("provinces and districts open at their department; the report keeps the exact division"
            if (place and re.fullmatch(r"\d{4}(\d{2})?", place.strip())) else None)
    return {"action_id": spec["id"], "kind": action, "label": text, "shown_to_user_as": "button",
            "target": {k: spec[k] for k in ("country", "department", "year", "month")}, **({"note": note} if note else {})}


class Tool:
    def __init__(self, name: str, description: str, properties: dict[str, Any], run: Callable[..., dict[str, Any]]):
        self.name, self.description, self.properties, self.run = name, description, properties, run

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "strict": True,
                "input_schema": {"type": "object", "properties": self.properties,
                                 "required": list(self.properties), "additionalProperties": False}}


PLACE = nullable("string", "Territory: 'current' or null for the on-screen selection, a Peruvian department, "
                 "province or district name, a UBIGEO code (2, 4 or 6 digits) or a country name.")
YEAR = nullable("integer", "Year (2002 to the current year); null = the on-screen year.")
MONTH = nullable("integer", "Calendar month 1-12; null = the on-screen month.")
TOOL_LIST = [
    Tool("territory_profile",
         "Evidence for one territory and month: activity against its normal (median, p10-p90 band, rank), the Jul-Oct "
         "fire season, harmonized versus raw-pixel trend since 2003 with annual totals, satellite fire events versus "
         "INDECI emergencies (Peru), Hansen tree-cover loss, NASA POWER climate context (Peru) and data quality. "
         "Use it first for almost any question about a place.",
         {"place": PLACE, "year": YEAR, "month": MONTH}, run_territory_profile),
    Tool("activity_series",
         "Monthly harmonized values of one territory from 2002: filter by calendar month (e.g. every September) or by "
         "years. Null values are gaps or non-comparable months, never zero.",
         {"place": PLACE, "month": nullable("integer", "Calendar month 1-12, or null for all months."),
          "year_start": nullable("integer", "First year, or null."), "year_end": nullable("integer", "Last year, or null.")},
         run_activity_series),
    Tool("compare_departments",
         "Peru's departments side by side for one month: activity, anomaly and rank of the month, fire-season rank, "
         "harmonized and raw trends, significant fire events, INDECI emergencies, tree-cover loss and drought. Each "
         "indicator is separate; there is no composite score. Peru only; the first call for a month can take ~20 s.",
         {"year": YEAR, "month": MONTH,
          "sort_by": nullable("string", "Ordering criterion (default month_anomaly).", enum=sorted(SORTS)),
          "limit": nullable("integer", "Number of departments to return, 1-25 (default 10).")},
         run_compare_departments),
    Tool("validation_summary",
         "How trustworthy the harmonization is: validation gates, leave-one-year-out results for the MODIS calibration "
         "and the NOAA-20 bridge, per-biome strata of a country, transfer to non-calibration countries and the "
         "static-source mask.",
         {"country": nullable("string", "Country for the per-stratum detail; null = the on-screen country.")},
         run_validation_summary),
    Tool("method_notes",
         "Documented method and definitions, with their source documents.",
         {"topic": {"type": "string", "enum": sorted(NOTES), "description": "Topic of the note."}}, run_method_notes),
    Tool("find_territory",
         "Find Peruvian departments, provinces or districts (with UBIGEO codes) or a country by name.",
         {"name": {"type": "string", "description": "Place name, accents optional."}}, run_find_territory),
    Tool("show_visual",
         "Show the user a chart or table under your answer, drawn from NINA's own results (the numbers come from "
         "NINA, not from you). Kinds: " + "; ".join(f"{k}: {v}" for k, v in VISUAL_KINDS.items()) + ". At most "
         "three per answer. The result returns the same numbers so you can refer to them.",
         {"kind": {"type": "string", "enum": sorted(VISUAL_KINDS), "description": "What to show."},
          "place": PLAIN_PLACE, "year": PLAIN_YEAR, "month": PLAIN_MONTH},
         run_show_visual),
    Tool("propose_action",
         "Offer the user a button that operates NINA's interface: " + "; ".join(f"{k}: {v}" for k, v in
                                                                         ACTION_KINDS.items())
         + ". Use it when the user asks to see, open, go to, compare on the map, print or download something. You "
         "cannot press it yourself; say that the button is below the answer.",
         {"action": {"type": "string", "enum": sorted(ACTION_KINDS), "description": "Interface action."},
          "place": PLAIN_PLACE, "year": PLAIN_YEAR, "month": PLAIN_MONTH,
          "label": {"type": "string", "description": "Short button text in the answer language (max 80 "
                    "characters); empty = default text."}},
         run_propose_action),
    Tool("calculate",
         "Arithmetic on figures already returned by other tools (+ - * / and parentheses), for ratios, differences "
         "or shares. Every operand must come from an earlier tool result; 100 and 1000 are allowed as constants.",
         {"expression": {"type": "string", "description": "For example (20909.5 - 14081) / 14081 * 100"}},
         run_calculate),
]
TOOLS = {tool.name: tool for tool in TOOL_LIST}
TOOL_SCHEMAS = [tool.schema() for tool in TOOL_LIST]


# ---------------------------------------------------------------- question understanding


def matcher(*fragments: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(fragments) + ")")


SCOPE = {
    "operational": matcher("EVACUAT", "DISPATCH", r"DEPLOY", "BRIGADE", r"SEND (?:TEAMS|FIREFIGHTERS|RESOURCES|HELP)",
                           "FIREFIGHTER", "EVACU", "BRIGADA", "DESPLEG", "BOMBERO",
                           r"ENVIAR (?:EQUIPOS|RECURSOS|BRIGADAS|AYUDA)"),
    "cause": matcher(r"CAUSE", r"WHO (?:STARTED|STARTS|SET)", "ARSON", "INTENTIONAL", "BLAME", r"CAUSA",
                     "PROVOCAD", "INTENCIONAL", r"CULPA", r"QUIEN (?:INICIO|PROVOCO|CAUSO)"),
    "damage": matcher("CASUALT", r"DEATHS?\b", r"DEAD\b", "INJURED", "PEOPLE AFFECTED", r"ECONOMIC (?:LOSS|DAMAGE)",
                      "AFECTADOS", "DAMNIFICAD", "FALLECID", "MUERTOS", "HERIDOS", r"DANOS\b"),
    "forecast": matcher("FORECAST", "PREDICT", "TOMORROW", r"NEXT (?:WEEK|MONTH|YEAR|SEASON)", r"WILL THERE BE",
                        "WILL BURN", r"SPREAD\b", "PRONOSTIC", "PREDEC", "PREDIC", r"MANANA\b",
                        r"PROXIM[OA] (?:SEMANA|MES|ANO|TEMPORADA)", r"HABRA\b", "VA A HABER", "SE QUEMARA", "PROPAGA"),
}
INTENTS = [
    ("burned", matcher("BURNED AREA", "BURNT AREA", "AREA QUEMADA", "SUPERFICIE QUEMADA", "HECTAREAS QUEMADAS",
                       r"HA QUEMADAS", "MCD64", "AREA BURNED", "HECTARES BURNED", "SE QUEMARON", "QUEMADAS")),
    ("compare", matcher(r"WHICH (?:DEPARTMENTS?|REGIONS?)", r"WHAT (?:DEPARTMENTS?|REGIONS?)", r"DEPARTMENTS\b",
                        r"REGIONS\b", "RANKING", "RANK THE", "PRIORIT", "STAND OUT", "MOST AFFECTED",
                        r"QUE (?:DEPARTAMENTOS?|REGION(?:ES)?)", r"CUAL(?:ES)? (?:DEPARTAMENTOS?|REGION(?:ES)?)",
                        r"DEPARTAMENTOS\b", r"REGIONES\b", "PRIORI", "DESTACA", "MAS AFECTAD")),
    ("trend", matcher("TREND", "INCREAS", "DECREAS", "LONG-TERM", "LONG TERM", "OVER THE YEARS", "OVER TIME",
                      "GROWING", "ARTEFACT", "ARTIFACT", "TENDENCIA", "AUMENT", "DISMINU", "A LO LARGO", "CRECIEND",
                      "MORE FIRES THAN", "MAS INCENDIOS QUE")),
    ("validation", matcher("VALIDA", "RELIAB", "ACCURA", "UNCERTAIN", r"ERRORS?\b", r"BIAS", r"GATES?\b", "TRUST",
                           "HOW GOOD", "LEAVE-ONE", r"LOYO\b", "FIABLE", "CONFIABLE", "PRECISION", "INCERTIDUMBRE",
                           "SESGO", "CONFIANZA", "QUE TAN BUEN", "ROBUST")),
    ("events", matcher("EMERGENC", "INDECI", "SINPAD", r"EVENTS?\b", "EVENTO", "HOW MANY FIRES", "NUMBER OF FIRES",
                       "CUANTOS INCENDIOS", "NUMERO DE INCENDIOS", "INCENDIOS DETECTADOS", "DETECTED FIRES",
                       "REGISTERED", "REGISTRAD")),
    ("forest", matcher("FOREST", "BOSQUE", r"TREES?\b", "TREE-COVER", "ARBOL", "ARBOREA", "DEFOREST", "HANSEN",
                       "PERDIDA", r"LOSS\b", "HECTARE", "HECTAREA")),
    ("climate", matcher("CLIMAT", "CLIMA", "DROUGHT", "SEQUIA", "RAIN", "LLUVIA", "PRECIP", r"DRY\b", "DRIER",
                        r"SEC[OA]S?\b", r"VAPOU?R", r"VPD\b", "TEMPERAT", "WEATHER", r"NINO\b")),
    ("quality", matcher("COVERAGE", r"COBERTURA\b(?! ARBOREA)", r"GAPS?\b", "VACIO", "MISSING", r"FALTA",
                        "PROVISIONAL", "INCOMPLET", "PARTIAL", "PARCIAL", "QUALITY", "CALIDAD", "SUFFICIENT",
                        "SUFICIENT", "CLOUD", "NUBE", "SUPPORT", "SOPORTE")),
    ("season", matcher("SEASON", "TEMPORADA", "JUL-OCT", "JULY TO OCTOBER", "JULIO A OCTUBRE")),
    ("method", matcher("HARMONI", "ARMONI", "CALIBRA", "MODIS", "VIIRS", "SENSOR", "SATELLITE", "SATELIT", "NOAA",
                       "S-NPP", r"SNPP\b", r"UNITS?\b", "UNIDAD", "CELL-DAY", "CELDA", r"H3\b", "METHOD", "METODO",
                       r"COMO SE (?:CALCULA|MIDE|OBTIENE)", "COMO FUNCIONA", r"MASK", "MASCARA", "VOLCAN",
                       r"SOURCES?\b", r"FUENTES?\b", "LIMITATION", "LIMITACION", r"WHAT CAN(?:NOT|'T)? NINA",
                       r"QUE (?:NO )?PUEDE NINA")),
]
VALIDATION_WORDS = dict(INTENTS)["validation"]
NOT_A_CAUSE = matcher("SENSOR", "MODIS", "VIIRS", "HARMONI", "ARMONI", "ARTEFACT", "ARTIFACT", "ARTEFACTO",
                      "SATELLITE", "SATELIT", "CALIBRA", "METHOD", "METODO")
METHOD_TOPICS = [
    ("noaa20_bridge", matcher("NOAA", "BRIDGE", "PUENTE")),
    ("static_mask", matcher("MASK", "MASCARA", "VOLCAN", "STATIC", "ESTATIC", "FLARE", "URBAN")),
    ("unit", matcher(r"UNITS?\b", "UNIDAD", "CELL", "CELDA", r"H3\b")),
    ("limitations", matcher("LIMIT", r"CAN(?:NOT|'T)", "NOT ANSWER", "NO PUEDE")),
    ("sources", matcher(r"SOURCES?\b", r"FUENTES?\b")),
    ("gaps", matcher(r"GAPS?\b", "VACIO", "OUTAGE")),
]
SORT_WORDS = [
    ("emergencies", matcher("EMERGENC", "INDECI")), ("forest_loss", matcher("FOREST", "BOSQUE", "TREE", "ARBOL", "PERDIDA")),
    ("events", matcher(r"EVENTS?\b", "EVENTO", "DETECTED FIRES", "INCENDIOS DETECTADOS")),
    ("trend", matcher("TREND", "TENDENCIA")), ("season", matcher("SEASON", "TEMPORADA")),
]


def classify(question: str) -> tuple[str, str | None]:
    """(intent, scope kind); intent 'scope' means NINA cannot answer the question."""
    text = fold(question)
    for kind, pattern in SCOPE.items():
        if pattern.search(text) and not (kind == "cause" and NOT_A_CAUSE.search(text)):
            return "scope", kind
    for intent, pattern in INTENTS:
        if pattern.search(text):
            return intent, None
    return "overview", None


def month_in(text: str) -> int | None:
    for language in ("en", "es"):
        for index, name in enumerate(MONTH_NAMES[language]):
            key = fold(name)
            pattern = r"\b(?:IN|OF|DURING) MAY\b|\bMAY (?:20\d\d|\d{1,2})\b" if key == "MAY" else rf"\b{key}\b"
            if re.search(pattern, text):
                return index + 1
    return 9 if re.search(r"\bSEPTIEMBRE\b|\bSEPT\b", text) else None


def period_in(question: str, context: AnalystContext) -> tuple[int, int]:
    text = fold(question)
    years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", text) if 2002 <= int(y) <= date.today().year]
    return (years[-1] if years else context.year), (month_in(text) or context.month)


def place_in(question: str) -> str | None:
    """A Peruvian department, province or country named in the question (None = the on-screen territory)."""
    text = fold(question)
    named = re.search(r"\b(?:DISTRITO DE|DISTRICT OF|PROVINCIA DE|PROVINCE OF) ([A-Z][A-Z ]{2,40})", text)
    if named:
        words = named.group(1).split()
        for size in range(len(words), 0, -1):
            exact = [m for m in find_divisions(" ".join(words[:size]), 3) if m["key"] == " ".join(words[:size])]
            if exact:
                return exact[0]["ubigeo"]
    rows = sorted(divisions(), key=lambda r: -len(r["key"]))
    for level, minimum in (("department", 3), ("province", 6)):
        for row in rows:
            if row["level"] == level and len(row["key"]) >= minimum and re.search(rf"\b{re.escape(row['key'])}\b", text):
                return row["ubigeo"]
    for key, name in sorted(country_names().items(), key=lambda item: -len(item[0])):
        if len(key) >= 4 and re.search(rf"\b{re.escape(key)}\b", text):
            return name
    return None


# ---------------------------------------------------------------- deterministic engine

TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "overview": "{name} · {month} {year}. {headline}",
        "report_hint": "The technical report (charts, imagery and sources) opens with the “Technical report” button.",
        "trend": "{name}, {start}–{end}: the harmonized series shows {harm}. The raw pixel count, which mixes MODIS and "
        "VIIRS, would show {raw}.",
        "trend_words": {"increase": "a significant increase ({slope} %/year, p {p})",
                        "decrease": "a significant decrease ({slope} %/year, p {p})",
                        "no_trend": "no significant trend ({slope} %/year, p {p})",
                        "insufficient": "too few years for a trend"},
        "trend_artefact": "The rise in the raw count is largely a sensor artefact: from 2012 VIIRS detects more pixels "
        "per fire than MODIS. Only the harmonized series is comparable across the whole period.",
        "trend_agree": "Both series point the same way; the harmonized slope is the one comparable across sensors.",
        "trend_hidden": "The harmonized series shows a change that the raw count does not reveal.",
        "trend_differ": "The two series disagree; the harmonized one is the comparable reference.",
        "trend_flat": "Neither series shows a significant trend.",
        "top_years": "Highest harmonized years: {years}.",
        "trend_method": "Method: Theil–Sen slope as a share of the median per year and Mann–Kendall test at p < {alpha}; "
        "the current, incomplete year is excluded.",
        "modis_caveat": "Values before 2012 depend on the MODIS calibration, which is still experimental.",
        "trend_none": "There are not enough complete years to estimate a trend for {name}.",
        "events": "{name}, {year}: {significant} significant fire events detected by satellite ({total} events in all).",
        "events_indeci": "INDECI registered {emergencies} forest-fire emergencies in the same year.",
        "events_no_indeci": "There are no INDECI records for this territory and year (INDECI covers Peruvian districts "
        "only).",
        "indeci_partial": "INDECI records in the layer end on {through}, so that year is incomplete.",
        "events_top": "Most active subdivisions (detected events / INDECI emergencies): {items}.",
        "events_meaning": "A significant event is a cluster of at least 5 active cell-days; an INDECI emergency is an "
        "official record with damage assessment. They measure different things and neither validates the other.",
        "events_pre_viirs": "Fire events are computed for the VIIRS era only (from 2012); {year} is earlier.",
        "events_check": "Measured agreement ({registry}, {start}–{end}): {rate} % of registered records coincide with a "
        "detected event in the same place within ±3 days, against {chance} % by chance; only {share} % of significant "
        "detected events were registered.",
        "events_check_department": "In {department}: {rate} % of {records} records, against {chance} % by chance.",
        "events_check_weak": "The comparison with {registry} is not informative at this scale: {rate} % of records "
        "coincide with a detected event, but {chance} % would by chance.",
        "events_none": "No fire events were detected in {name} in {year}.",
        "forest_gfw": "{name}, {year}: {loss} ha of tree-cover loss (Hansen/UMD, Global Forest Watch statistics), of which {fire} ha in 1 km cells where wildfire was the dominant driver.",
        "forest": "{name}, {year}: {loss} ha of tree-cover loss (Hansen/UMD), of which {fire} ha in cells with satellite "
        "fire activity in the same or the previous year.",
        "forest_last": "The Hansen/UMD layer ends in {last}.",
        "forest_2000": "Tree cover in 2000 (canopy of at least 30 %): {ha} ha.",
        "forest_caveats": "Tree-cover loss is not deforestation (it includes fire-killed forest and plantation harvest), "
        "'with fire' means co-location rather than causation, and trends should not be read across the 2011–2012 "
        "method change.",
        "climate_intro": "Climate context for {month} {year} (CHIRPS rainfall, NASA POWER air dryness; anomalies against 2002–2024):",
        "climate_row": "{department}: {precip} mm of precipitation (percentile {percentile}, z = {z}); vapour-pressure "
        "deficit z = {vz}; drought: {drought}.",
        "drought": {True: "yes", False: "no", None: "not applicable (climatologically dry month)"},
        "climate_note": "Drought means low precipitation together with a high vapour-pressure deficit (both beyond one "
        "standard deviation). This is context only and does not attribute the fire activity to the weather.",
        "climate_none": "No climate context is available here: {reason}.",
        "quality": "{month} {year}: {valid} of {expected} region-days have valid archive support; status: {status}.",
        "quality_filled": "{days} day(s) were filled from NOAA-20 through the bridge.",
        "quality_provisional": "The month includes provisional near-real-time data that the standard product will "
        "replace.",
        "quality_validation": {"validated": "The harmonized record has passed its validation gates.",
                               "experimental": "The harmonized record is an experimental candidate: not all "
                               "validation gates pass."},
        "quality_clouds": "Cloud-free observation opportunities are not reconstructed, so a low value can reflect clouds "
        "as well as less fire.",
        "status": {"complete": "complete", "partial_archive": "partial archive", "provisional": "provisional",
                   "incomplete_coverage": "incomplete coverage", "unvalidated_domain": "outside the validated domain",
                   "not_available": "not available"},
        "season": "{name}, fire season (July–October) {year}: {value} units, rank {rank} of {rank_of}, {anomaly} % "
        "against the median of the other years.",
        "season_few": "{name}, fire season (July–October) {year}: {value} units; too few comparable years for a rank.",
        "season_none": "The fire season (July–October) {year} is not complete or has no comparable value for {name}.",
        "validation_status": "Validation status: {status} (method {version}).",
        "status_words": {True: "validated and published", False: "experimental candidate, not all gates passed"},
        "validation_link": "{link}, leave-one-year-out {start}–{end}: {passing} % of strata pass (required {required} %, "
        "with absolute bias of at most {bias} % and Spearman of at least {spearman}): {verdict}. Aggregate bias "
        "{aggregate} %; yearly error median {median} %, p90 {p90} %.",
        "link_names": {"terra_aqua": "MODIS Terra+Aqua to VIIRS S-NPP", "noaa20": "NOAA-20 to S-NPP bridge"},
        "verdict": {True: "gate passed", False: "gate not passed"},
        "validation_country": "{country}: {passed} of {total} evaluable strata pass for the MODIS calibration: {items}.",
        "stratum": "{biome} ({bias} %, Spearman {spearman}, {mark})",
        "mark": {True: "passes", False: "fails"},
        "validation_transfer": "{country} is not a calibration country ({countries}); its MODIS-era values use transferred "
        "coefficients. A 2026 diagnostic outside those countries gave {bias} % bias for MODIS Terra+Aqua and {bridge} % "
        "for the NOAA-20 bridge.",
        "validation_mask": "The static-source mask also fails its gate. Values from 2012 onwards rely on observed VIIRS "
        "and do not depend on the MODIS calibration.",
        "validation_short": "This dataset carries no per-stratum validation details.",
        "trust_link": "Values before 2012 come from the MODIS calibration, which passes in {passing} % of strata "
        "(required {required} %); in the strata that pass, the yearly error has a median of {median} % and a p90 of "
        "{p90} %.",
        "trust_country": "In {country}, {passed} of {total} evaluable strata pass.",
        "trust_viirs": "From 2012 the series is observed VIIRS, so the recent part of the trend does not depend on that "
        "calibration.",
        "compare_intro": "{month} {year}: {count} Peruvian departments compared by {criterion}. Leading departments:",
        "criteria": {"month_anomaly": "activity against their normal", "month_value": "activity in the month",
                     "season": "fire-season rank", "trend": "harmonized trend",
                     "events": "significant fire events in the year", "emergencies": "INDECI emergencies in the year",
                     "forest_loss": "tree-cover loss in the year"},
        "rows": {"month_anomaly": "{name}: {anomaly} % against its normal ({value} units, rank {rank} of {rank_of})",
                 "month_value": "{name}: {value} units ({anomaly} % against its normal)",
                 "season": "{name}: fire season ranked {season_rank} of {season_rank_of} ({season_anomaly} %)",
                 "trend": "{name}: {trend} %/year harmonized; {trend_raw} %/year in raw pixels",
                 "events": "{name}: {events} significant events; {emergencies} INDECI emergencies",
                 "emergencies": "{name}: {emergencies} INDECI emergencies; {events} significant events",
                 "forest_loss": "{name}: {loss} ha of tree-cover loss ({fire} ha with fire)"},
        "compare_empty": "No department has a comparable value for {criterion} in {month} {year}.",
        "compare_note": "Each indicator is reported separately; NINA does not combine them into a single score. The full "
        "sortable table is in the Priorities tab.",
        "method_more": "Ask how reliable the harmonization is to see its validation results for this territory.",
        "burned_month": "Burned area in {unit}, {month} {year} (MODIS MCD64A1, aggregated by GWIS): {area} ha, rank {rank} of {of} for that month (median of the other years {median} ha).",
        "burned_ends": "The MODIS MCD64A1 burned-area table (GWIS) ends in {end}; the month asked about is not covered yet.",
        "burned_year": "Whole year {year}: {area} ha.",
        "burned_caveat": "MCD64A1 is a 500 m product independent of the hotspots NINA harmonizes; it often misses fires much smaller than one pixel (about 25 ha).",
        "scope": {
            "forecast": "NINA does not forecast fires or their spread: it describes activity already detected by "
            "satellites and compares it with the territory's own history.",
            "cause": "NINA cannot attribute causes (natural, accidental or intentional): satellites detect heat, not who "
            "or what started a fire.",
            "operational": "NINA does not give operational instructions such as evacuations or brigade deployment: those "
            "decisions belong to the competent authorities, and FIRMS data are not suitable for tactical or local-scale "
            "decisions.",
            "burned_area": "NINA does not measure burned area: its unit is active cell-days of detected activity. The "
            "reference burned-area product is MODIS MCD64A1; NINA offers tree-cover loss (Hansen/UMD) as forest context.",
            "damage": "NINA does not hold figures on people affected or economic damage: it uses only the number of INDECI "
            "emergency records.",
        },
        "scope_offer": "It can compare {month} {year} in {name} with previous years, show the harmonized trend, contrast "
        "detected events with INDECI emergencies, or give forest-loss and climate context.",
        "tool_failed": "The data needed for this question are not available: {reason}",
    },
    "es": {
        "overview": "{name} · {month} de {year}. {headline}",
        "report_hint": "El informe técnico (gráficos, imágenes y fuentes) se abre con el botón «Informe técnico».",
        "trend": "{name}, {start}–{end}: la serie armonizada muestra {harm}. El conteo crudo de píxeles, que mezcla MODIS "
        "y VIIRS, mostraría {raw}.",
        "trend_words": {"increase": "un aumento significativo ({slope} %/año, p {p})",
                        "decrease": "una disminución significativa ({slope} %/año, p {p})",
                        "no_trend": "ninguna tendencia significativa ({slope} %/año, p {p})",
                        "insufficient": "años insuficientes para una tendencia"},
        "trend_artefact": "El aumento del conteo crudo es en gran parte un artefacto del sensor: desde 2012 VIIRS detecta "
        "más píxeles por incendio que MODIS. Solo la serie armonizada es comparable en todo el período.",
        "trend_agree": "Ambas series apuntan en la misma dirección; la pendiente armonizada es la comparable entre "
        "sensores.",
        "trend_hidden": "La serie armonizada muestra un cambio que el conteo crudo no revela.",
        "trend_differ": "Las dos series discrepan; la armonizada es la referencia comparable.",
        "trend_flat": "Ninguna de las dos series muestra una tendencia significativa.",
        "top_years": "Años armonizados más altos: {years}.",
        "trend_method": "Método: pendiente de Theil–Sen como proporción de la mediana por año y prueba de Mann–Kendall con "
        "p < {alpha}; se excluye el año en curso, incompleto.",
        "modis_caveat": "Los valores anteriores a 2012 dependen de la calibración de MODIS, que aún es experimental.",
        "trend_none": "No hay suficientes años completos para estimar una tendencia en {name}.",
        "events": "{name}, {year}: {significant} eventos de incendio significativos detectados por satélite ({total} "
        "eventos en total).",
        "events_indeci": "INDECI registró {emergencies} emergencias por incendio forestal en el mismo año.",
        "events_no_indeci": "No hay registros de INDECI para este territorio y año (INDECI cubre solo distritos del Perú).",
        "indeci_partial": "Los registros de INDECI de la capa terminan el {through}, por lo que ese año está incompleto.",
        "events_top": "Subdivisiones con más actividad (eventos detectados / emergencias INDECI): {items}.",
        "events_meaning": "Un evento significativo es un conglomerado de al menos 5 celdas-día activas; una emergencia de "
        "INDECI es un registro oficial con evaluación de daños. Miden cosas distintas y ninguna valida a la otra.",
        "events_pre_viirs": "Los eventos de incendio se calculan solo para la era VIIRS (desde 2012); {year} es anterior.",
        "events_check": "Concordancia medida ({registry}, {start}–{end}): el {rate} % de los registros coincide con un "
        "evento detectado en el mismo lugar dentro de ±3 días, frente a {chance} % por azar; solo el {share} % de los "
        "eventos significativos detectados fue registrado.",
        "events_check_department": "En {department}: {rate} % de {records} registros, frente a {chance} % por azar.",
        "events_check_weak": "La comparación con {registry} no es informativa a esta escala: el {rate} % de los registros "
        "coincide con un evento detectado, pero el {chance} % lo haría por azar.",
        "events_none": "No se detectaron eventos de incendio en {name} en {year}.",
        "forest_gfw": "{name}, {year}: {loss} ha de pérdida de cobertura arbórea (Hansen/UMD, estadísticas de Global Forest Watch), de las cuales {fire} ha en celdas de 1 km donde el incendio fue la causa dominante.",
        "forest": "{name}, {year}: {loss} ha de pérdida de cobertura arbórea (Hansen/UMD), de las cuales {fire} ha en "
        "celdas con actividad de fuego satelital el mismo año o el anterior.",
        "forest_last": "La capa de Hansen/UMD termina en {last}.",
        "forest_2000": "Cobertura arbórea en 2000 (dosel de al menos 30 %): {ha} ha.",
        "forest_caveats": "La pérdida de cobertura arbórea no es deforestación (incluye bosque muerto por fuego y cosecha "
        "de plantaciones), 'con fuego' indica coincidencia y no causalidad, y no deben leerse tendencias a través del "
        "cambio de método de 2011–2012.",
        "climate_intro": "Contexto climático de {month} de {year} (lluvia CHIRPS, sequedad del aire NASA POWER; anomalías respecto de 2002–2024):",
        "climate_row": "{department}: {precip} mm de precipitación (percentil {percentile}, z = {z}); déficit de presión "
        "de vapor z = {vz}; sequía: {drought}.",
        "drought": {True: "sí", False: "no", None: "no aplica (mes climatológicamente seco)"},
        "climate_note": "Sequía significa precipitación baja junto con un déficit de presión de vapor alto (ambos más allá "
        "de una desviación estándar). Es solo contexto y no atribuye la actividad de fuego al clima.",
        "climate_none": "No hay contexto climático disponible aquí: {reason}.",
        "quality": "{month} de {year}: {valid} de {expected} combinaciones región/día tienen soporte válido en el archivo; "
        "estado: {status}.",
        "quality_filled": "{days} día(s) se completaron con NOAA-20 mediante el puente.",
        "quality_provisional": "El mes incluye datos provisionales casi en tiempo real que el producto estándar "
        "reemplazará.",
        "quality_validation": {"validated": "El registro armonizado superó sus puertas de validación.",
                               "experimental": "El registro armonizado es un candidato experimental: no todas las "
                               "puertas de validación aprueban."},
        "quality_clouds": "Las oportunidades de observación sin nubes no se reconstruyen, por lo que un valor bajo puede "
        "deberse a nubes y no solo a menos fuego.",
        "status": {"complete": "completo", "partial_archive": "archivo parcial", "provisional": "provisional",
                   "incomplete_coverage": "cobertura incompleta", "unvalidated_domain": "fuera del dominio validado",
                   "not_available": "no disponible"},
        "season": "{name}, temporada de incendios (julio–octubre) {year}: {value} unidades, puesto {rank} de {rank_of}, "
        "{anomaly} % respecto de la mediana de los demás años.",
        "season_few": "{name}, temporada de incendios (julio–octubre) {year}: {value} unidades; pocos años comparables "
        "para un puesto.",
        "season_none": "La temporada de incendios (julio–octubre) {year} no está completa o no tiene un valor comparable "
        "en {name}.",
        "validation_status": "Estado de validación: {status} (método {version}).",
        "status_words": {True: "validado y publicado", False: "candidato experimental, no todas las puertas aprueban"},
        "validation_link": "{link}, validación dejando un año fuera {start}–{end}: aprueba el {passing} % de los estratos "
        "(se exige {required} %, con sesgo absoluto de hasta {bias} % y Spearman de al menos {spearman}): {verdict}. "
        "Sesgo agregado {aggregate} %; error anual mediano {median} %, p90 {p90} %.",
        "link_names": {"terra_aqua": "MODIS Terra+Aqua a VIIRS S-NPP", "noaa20": "Puente NOAA-20 a S-NPP"},
        "verdict": {True: "puerta aprobada", False: "puerta no aprobada"},
        "validation_country": "{country}: {passed} de {total} estratos evaluables aprueban la calibración de MODIS: "
        "{items}.",
        "stratum": "{biome} ({bias} %, Spearman {spearman}, {mark})",
        "mark": {True: "aprueba", False: "no aprueba"},
        "validation_transfer": "{country} no es un país de calibración ({countries}); sus valores de la era MODIS usan "
        "coeficientes transferidos. Un diagnóstico de 2026 fuera de esos países dio un sesgo de {bias} % para MODIS "
        "Terra+Aqua y de {bridge} % para el puente NOAA-20.",
        "validation_mask": "La máscara de fuentes estáticas tampoco aprueba su puerta. Los valores desde 2012 se basan en "
        "VIIRS observado y no dependen de la calibración de MODIS.",
        "validation_short": "Este conjunto de datos no incluye detalles de validación por estrato.",
        "trust_link": "Los valores anteriores a 2012 provienen de la calibración de MODIS, que aprueba en el {passing} % "
        "de los estratos (se exige {required} %); en los estratos que aprueban, el error anual tiene una mediana de "
        "{median} % y un p90 de {p90} %.",
        "trust_country": "En {country}, aprueban {passed} de {total} estratos evaluables.",
        "trust_viirs": "Desde 2012 la serie es VIIRS observado, por lo que el tramo reciente de la tendencia no depende "
        "de esa calibración.",
        "compare_intro": "{month} de {year}: {count} departamentos del Perú comparados por {criterion}. Departamentos "
        "destacados:",
        "criteria": {"month_anomaly": "actividad frente a su normal", "month_value": "actividad del mes",
                     "season": "puesto de la temporada", "trend": "tendencia armonizada",
                     "events": "eventos de incendio significativos del año", "emergencies": "emergencias INDECI del año",
                     "forest_loss": "pérdida de cobertura arbórea del año"},
        "rows": {"month_anomaly": "{name}: {anomaly} % frente a su normal ({value} unidades, puesto {rank} de {rank_of})",
                 "month_value": "{name}: {value} unidades ({anomaly} % frente a su normal)",
                 "season": "{name}: temporada en el puesto {season_rank} de {season_rank_of} ({season_anomaly} %)",
                 "trend": "{name}: {trend} %/año armonizado; {trend_raw} %/año en píxeles crudos",
                 "events": "{name}: {events} eventos significativos; {emergencies} emergencias INDECI",
                 "emergencies": "{name}: {emergencies} emergencias INDECI; {events} eventos significativos",
                 "forest_loss": "{name}: {loss} ha de pérdida arbórea ({fire} ha con fuego)"},
        "compare_empty": "Ningún departamento tiene un valor comparable de {criterion} en {month} de {year}.",
        "compare_note": "Cada indicador se presenta por separado; NINA no los combina en un puntaje. La tabla completa y "
        "ordenable está en la pestaña Prioridades.",
        "method_more": "Pregunta qué tan fiable es la armonización para ver sus resultados de validación en este "
        "territorio.",
        "burned_month": "Área quemada en {unit}, {month} de {year} (MODIS MCD64A1, agregada por GWIS): {area} ha, puesto {rank} de {of} para ese mes (mediana de los demás años {median} ha).",
        "burned_ends": "La tabla de área quemada MODIS MCD64A1 (GWIS) termina en {end}; el mes consultado aún no está cubierto.",
        "burned_year": "Año completo {year}: {area} ha.",
        "burned_caveat": "MCD64A1 es un producto de 500 m independiente de los focos que NINA armoniza; suele omitir incendios mucho menores que un píxel (unas 25 ha).",
        "scope": {
            "forecast": "NINA no pronostica incendios ni su propagación: describe la actividad ya detectada por satélites "
            "y la compara con la historia del propio territorio.",
            "cause": "NINA no puede atribuir causas (naturales, accidentales o intencionales): los satélites detectan "
            "calor, no quién ni qué inició un incendio.",
            "operational": "NINA no da instrucciones operativas como evacuaciones o despliegue de brigadas: esas "
            "decisiones corresponden a las autoridades competentes, y los datos de FIRMS no son adecuados para "
            "decisiones tácticas o de escala local.",
            "burned_area": "NINA no mide área quemada: su unidad son celdas-día de actividad detectada. El producto de "
            "referencia de área quemada es MODIS MCD64A1; NINA ofrece la pérdida de cobertura arbórea (Hansen/UMD) como "
            "contexto forestal.",
            "damage": "NINA no tiene cifras de personas afectadas ni de daños económicos: usa solo el número de registros "
            "de emergencias de INDECI.",
        },
        "scope_offer": "Sí puede comparar {month} de {year} en {name} con años anteriores, mostrar la tendencia "
        "armonizada, contrastar eventos detectados con emergencias de INDECI o dar contexto de pérdida forestal y clima.",
        "tool_failed": "Los datos necesarios para esta pregunta no están disponibles: {reason}",
    },
}


def month_name(month: int, language: str) -> str:
    return MONTH_NAMES[language][month - 1]


def p_text(value: float | None, language: str) -> str:
    """'= 0.019' or '< 0.001'."""
    if value is None:
        return "= —"
    return f"< {format_number(P_FLOOR, language, 3)}" if value < P_FLOOR else f"= {format_number(value, language, 3)}"


class Composer:
    """Templated answers in the request language; every figure is read from a tool result."""

    def __init__(self, session: Session):
        self.session = session
        self.language = session.request.language
        self.t = TEXT[self.language]

    def n(self, value: Any, digits: int = 0, sign: bool = False) -> str:
        return format_number(value, self.language, digits, sign)

    def profile(self, place: str | None, year: int, month: int) -> dict[str, Any]:
        return self.session.call("territory_profile", place=place, year=year, month=month)

    def overview(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        text = self.t["overview"].format(name=p["territory"]["name"], month=month_name(month, self.language),
                                         year=year, headline=p["headline"])
        lines = "\n".join(f"- {line}" for line in p["summary"])
        caveat = f"\n\n{self.t['modis_caveat']}" if p["validation_status"] != "validated" else ""
        return f"{text}\n\n{lines}{caveat}\n\n{self.t['report_hint']}"

    def trend(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        trend = p["trend"]
        if not trend["period"]:
            return self.t["trend_none"].format(name=p["territory"]["name"])
        harm, raw = trend["harmonized"], trend["raw_pixels"]

        def words(item: dict[str, Any]) -> str:
            return self.t["trend_words"][item["direction"]].format(
                slope=self.n(item["slope_pct_per_year"] or 0, 1, True), p=p_text(item["p_value"], self.language))

        start, end = trend["period"]
        parts = [self.t["trend"].format(name=p["territory"]["name"], start=start, end=end, harm=words(harm), raw=words(raw))]
        moving = {"increase", "decrease"}
        if raw["direction"] == "increase" and harm["direction"] != "increase":
            parts.append(self.t["trend_artefact"])
        elif harm["direction"] == raw["direction"] and harm["direction"] in moving:
            parts.append(self.t["trend_agree"])
        elif harm["direction"] in moving and raw["direction"] not in moving:
            parts.append(self.t["trend_hidden"])
        elif harm["direction"] in moving or raw["direction"] in moving:
            parts.append(self.t["trend_differ"])
        else:
            parts.append(self.t["trend_flat"])
        top = sorted((a for a in p["annual"] if start <= a["year"] <= end), key=lambda a: -a["harmonized"])[:3]
        if top:
            parts.append(self.t["top_years"].format(years=", ".join(f"{a['year']} ({self.n(a['harmonized'])})" for a in top)))
        parts.append(self.t["trend_method"].format(alpha=self.n(trend["significance_level"], 2)))
        if VALIDATION_WORDS.search(fold(self.session.request.question)):
            parts.append(self.validation_brief(place))
        elif p["validation_status"] != "validated":
            parts.append(self.t["modis_caveat"])
        return " ".join(parts)

    def validation_brief(self, place: str | None) -> str:
        """Validation of the MODIS calibration where the trend is read (for 'can I trust the trend?')."""
        context = self.session.request.context
        country = place if place and not place.isdigit() else ("Peru" if place or context.ubigeo else None)
        v = self.session.call("validation_summary", country=country)
        if "links" not in v:
            return self.t["validation_short"]
        link = v["links"]["terra_aqua"]
        parts = [self.t["trust_link"].format(passing=self.n(link["strata_passing_percent"], 1),
                                             required=self.n(link["required_percent"]),
                                             median=self.n(link["yearly_error_median_percent"], 1),
                                             p90=self.n(link["yearly_error_p90_percent"], 1))]
        if v["country_is_calibration_country"]:
            counts = v["country_strata_counts"]["terra_aqua"]
            parts.append(self.t["trust_country"].format(country=v["country"], passed=counts["passed"],
                                                        total=counts["evaluable"]))
        parts.append(self.t["trust_viirs"])
        return " ".join(parts)

    def events(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        events, name = p["events"], p["territory"]["name"]
        if events["status"] != "available":
            return self.t["tool_failed"].format(reason=events.get("reason") or events["status"])
        if year < 2012:
            return self.t["events_pre_viirs"].format(year=year)
        row = events["selected_year"]
        if not row:
            return self.t["events_none"].format(name=name, year=year)
        parts = [self.t["events"].format(name=name, year=year, significant=self.n(row["significant_events"]),
                                         total=self.n(row["events"]))]
        if row["emergencies"] is not None:
            parts.append(self.t["events_indeci"].format(emergencies=self.n(row["emergencies"])))
            through = (events.get("emergencies_coverage") or [None, None])[1]
            if through and int(through[:4]) == year and not through.endswith("12-31"):
                parts.append(self.t["indeci_partial"].format(through=through))
        else:
            parts.append(self.t["events_no_indeci"])
        top = [x for x in events["top_subdivisions"] if x["events"] or x["emergencies"]][:3]
        if top:
            parts.append(self.t["events_top"].format(items="; ".join(
                f"{x['name']} ({self.n(x['events'])} / {self.n(x['emergencies'])})" for x in top)))
        parts.append(self.t["events_meaning"])
        check = events.get("validation_against_registry")
        if check and check.get("informative") is False:
            parts.append(self.t["events_check_weak"].format(
                registry=check["registry"], rate=self.n(100 * check["rate"]), chance=self.n(100 * check["chance_rate"])))
        elif check:
            parts.append(self.t["events_check"].format(
                registry=check["registry"], start=check["period"][0][:4], end=check["period"][1][:4],
                rate=self.n(100 * check["rate"]), chance=self.n(100 * check["chance_rate"]),
                share=self.n(100 * check["registered_share"], 1)))
            department = check.get("department")
            if department:
                parts.append(self.t["events_check_department"].format(
                    department=reports.display_name(department["department"]), records=self.n(department["records"]),
                    rate=self.n(100 * department["rate"]), chance=self.n(100 * department["chance_rate"])))
        return " ".join(parts)

    def burned(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        burned = p["burned_area"]
        if burned["status"] != "available":
            return self.t["tool_failed"].format(reason=burned.get("reason") or burned["status"])
        parts = []
        month_row = burned.get("selected_month")
        if month_row:
            parts.append(self.t["burned_month"].format(
                unit=burned["unit"], month=month_name(month_row["month"], self.language), year=month_row["year"],
                area=self.n(month_row["burned_ha"]), rank=month_row["rank"], of=month_row["rank_of"],
                median=self.n(month_row["median_other_years_ha"])))
        else:
            parts.append(self.t["burned_ends"].format(end=burned["coverage"][1]))
        year_row = burned.get("selected_year") or (burned["by_year"][-1] if burned["by_year"] else None)
        if year_row:
            parts.append(self.t["burned_year"].format(year=year_row["year"], area=self.n(year_row["burned_ha"])))
        parts.append(self.t["burned_caveat"])
        return " ".join(parts)

    def forest(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        forest, name = p["forest"], p["territory"]["name"]
        if forest["status"] != "available":
            return self.t["tool_failed"].format(reason=forest.get("reason") or forest["status"])
        parts = []
        row = forest["selected_year"]
        if row is None:
            parts.append(self.t["forest_last"].format(last=forest["last_year_available"]))
            row = forest["by_year"][-1]
        template = self.t["forest_gfw"] if forest.get("source_kind") == "gfw_drivers" else self.t["forest"]
        parts.append(template.format(name=name, year=row["year"], loss=self.n(row["loss_ha"]),
                                             fire=self.n(row["loss_ha_with_fire"])))
        if forest["forest_2000_ha"]:
            parts.append(self.t["forest_2000"].format(ha=self.n(forest["forest_2000_ha"])))
        parts.append(self.t["forest_caveats"])
        return " ".join(parts)

    def climate(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        climate = p["climate"]
        if climate["status"] != "available":
            return self.t["climate_none"].format(reason=climate.get("reason") or climate["status"])
        rows = [self.t["climate_row"].format(
            department=reports.display_name(r["department"]), precip=self.n(r["precip_mm"], 1),
            percentile=self.n(r["precip_percentile"], 0), z=self.n(r["precip_z"], 2, True),
            vz=self.n(r["vpd_z"], 2, True), drought=self.t["drought"][r["drought"]]) for r in climate["selected_month"][:5]]
        intro = self.t["climate_intro"].format(month=month_name(month, self.language), year=year)
        return intro + "\n" + "\n".join(f"- {row}" for row in rows) + "\n\n" + self.t["climate_note"]

    def quality(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        quality, status = p["quality"], p["month"]["status"]
        parts = [self.t["quality"].format(month=month_name(month, self.language).capitalize(), year=year,
                                          valid=self.n(quality["valid_region_days"]),
                                          expected=self.n(quality["expected_region_days"]),
                                          status=self.t["status"].get(status, status))]
        if quality["noaa20_filled_days"]:
            parts.append(self.t["quality_filled"].format(days=self.n(quality["noaa20_filled_days"])))
        if quality["is_provisional"]:
            parts.append(self.t["quality_provisional"])
        parts.append(self.t["quality_validation"][quality["validation_status"]])
        parts.append(self.t["quality_clouds"])
        return " ".join(parts)

    def season(self, place, year, month, _scope) -> str:
        p = self.profile(place, year, month)
        season, name = p["season_jul_oct"], p["territory"]["name"]
        if season.get("value") is None:
            return self.t["season_none"].format(year=year, name=name)
        if season.get("anomaly_percent") is None:
            return self.t["season_few"].format(name=name, year=year, value=self.n(season["value"]))
        return self.t["season"].format(name=name, year=year, value=self.n(season["value"]), rank=season["rank"],
                                       rank_of=season["rank_of"], anomaly=self.n(season["anomaly_percent"], 0, True))

    def validation(self, place, year, month, _scope) -> str:
        context = self.session.request.context
        country = place if place and not place.isdigit() else ("Peru" if place or context.ubigeo else None)
        v = self.session.call("validation_summary", country=country)
        parts = [self.t["validation_status"].format(status=self.t["status_words"][v["is_published"]],
                                                    version=v["method_version"])]
        if "links" not in v:
            return " ".join(parts + [self.t["validation_short"]])
        for key in ("terra_aqua", "noaa20"):
            link = v["links"].get(key)
            if not link:
                continue
            start, end = link["years"]
            parts.append(self.t["validation_link"].format(
                link=self.t["link_names"][key], start=start, end=end, passing=self.n(link["strata_passing_percent"], 1),
                required=self.n(link["required_percent"]), bias=self.n(link["max_abs_bias_percent"]),
                spearman=self.n(link["min_spearman"], 1), verdict=self.t["verdict"][link["gate_passed"]],
                aggregate=self.n(link["aggregate_relative_bias_percent"], 2, True),
                median=self.n(link["yearly_error_median_percent"], 1), p90=self.n(link["yearly_error_p90_percent"], 1)))
        if v["country_is_calibration_country"]:
            strata = [s for s in v["country_strata"] if s["link"] == "terra_aqua" and s["evaluable"]]
            counts = v["country_strata_counts"]["terra_aqua"]
            items = "; ".join(self.t["stratum"].format(
                biome=BIOMES[self.language].get(s["biome_code"], s["biome"]), bias=self.n(s["relative_bias_percent"], 1, True),
                spearman=self.n(s["spearman"], 2), mark=self.t["mark"][s["passed"]]) for s in strata)
            parts.append(self.t["validation_country"].format(country=v["country"], passed=counts["passed"],
                                                             total=counts["evaluable"], items=items))
        elif v.get("outside_calibration_countries_2026"):
            outside = v["outside_calibration_countries_2026"]
            parts.append(self.t["validation_transfer"].format(
                country=v["country"], countries=", ".join(v["calibration_countries"]),
                bias=self.n((outside.get("terra_aqua") or {}).get("relative_bias_percent"), 1, True),
                bridge=self.n((outside.get("noaa20") or {}).get("relative_bias_percent"), 2, True)))
        if v["gates"] and v["gates"].get("static_mask") is False:
            parts.append(self.t["validation_mask"])
        return " ".join(parts)

    def method(self, place, year, month, _scope) -> str:
        text = fold(self.session.request.question)
        topic = next((name for name, pattern in METHOD_TOPICS if pattern.search(text)), "calibration")
        note = self.session.call("method_notes", topic=topic)
        extra = f" {self.t['method_more']}" if topic in {"calibration", "unit", "noaa20_bridge"} else ""
        return note["text"] + extra

    def compare(self, place, year, month, _scope) -> str:
        text = fold(self.session.request.question)
        sort_by = next((name for name, pattern in SORT_WORDS if pattern.search(text)), "month_anomaly")
        table = self.session.call("compare_departments", year=year, month=month, sort_by=sort_by, limit=5)
        key = SORTS[sort_by][0]
        rows = [row for row in table["rows"] if row[key] is not None]
        criterion = self.t["criteria"][sort_by]
        month_text = month_name(month, self.language)
        if not rows:
            return self.t["compare_empty"].format(criterion=criterion, month=month_text, year=year)
        def rank(value: int | None) -> str:
            return str(value) if value is not None else "—"

        lines = []
        for row in rows:
            lines.append(self.t["rows"][sort_by].format(
                name=row["name"], anomaly=self.n(row["month_anomaly"], 0, True), value=self.n(row["month_value"]),
                rank=rank(row["month_rank"]), rank_of=rank(row["month_rank_of"]), season_rank=rank(row["season_rank"]),
                season_rank_of=rank(row["season_rank_of"]), season_anomaly=self.n(row["season_anomaly"], 0, True),
                trend=self.n(row["trend_harmonized"], 1, True), trend_raw=self.n(row["trend_raw"], 1, True),
                events=self.n(row["significant_events"]), emergencies=self.n(row["emergencies"]),
                loss=self.n(row["forest_loss_ha"]), fire=self.n(row["forest_loss_with_fire_ha"])))
        intro = self.t["compare_intro"].format(month=month_text.capitalize(), year=year, count=table["departments"],
                                               criterion=criterion)
        return intro + "\n" + "\n".join(f"- {line}" for line in lines) + "\n\n" + self.t["compare_note"]

    def scope(self, place, year, month, kind) -> str:
        context = self.session.request.context
        return self.t["scope"][kind] + " " + self.t["scope_offer"].format(
            month=month_name(context.month, self.language), year=context.year,
            name=context_label(context, self.language).split(" (")[0])


def deterministic(session: Session) -> tuple[str, str]:
    """(answer, intent) from the classifier, the parsed place and period, and the tools."""
    request = session.request
    intent, kind = classify(request.question)
    place = place_in(request.question)
    year, month = period_in(request.question, request.context)
    composer = Composer(session)
    try:
        text = getattr(composer, intent)(place, year, month, kind)
    except ToolFailed as error:
        text = composer.t["tool_failed"].format(reason=error)
    action = requested_action(request.question) if intent != "scope" else None
    if action:
        session.run("propose_action", {"action": action, "place": place, "year": year, "month": month, "label": None})
    return text, intent


ACTION_WORDS = [
    ("download_data", matcher("DOWNLOAD", "DESCARG", "EXPORT")),
    ("open_report", matcher("REPORT", "INFORME", "PRINT", "IMPRIM", "PDF")),
    ("open_priorities", matcher("DEPARTMENT TABLE", "TABLA DE DEPARTAMENTOS", "PRIORIT")),
    ("open_calendar", matcher("CALENDAR", "CALENDARIO")),
    ("show_on_map", matcher("MAP", "MAPA", "ATLAS", "GO TO", "VE A", "LLEVAME", "MUESTRAME", "SHOW ME")),
]
ACTION_VERBS = matcher("SHOW", "OPEN", "GO TO", "TAKE ME", "DOWNLOAD", "EXPORT", "PRINT", "MUESTRA", "ABRE", "ABRIR",
                       "VE A", "LLEVAME", "DESCARG", "EXPORT", "IMPRIM", "VER ")


def requested_action(question: str) -> str | None:
    """The interface action a question asks for ('open the report of Cusco'), if any."""
    text = fold(question)
    if not ACTION_VERBS.search(text):
        return None
    return next((action for action, words in ACTION_WORDS if words.search(text)), None)


# ---------------------------------------------------------------- Claude engine

SYSTEM_PROMPT = """You are NINA's analyst. NINA is a harmonized record of satellite fire detections (NASA FIRMS: MODIS from 2000, VIIRS from 2012) for Peru and the world, with context layers for Peru: INEI districts, INDECI forest-fire emergencies, Hansen/UMD tree-cover loss and climate (CHIRPS rainfall, NASA POWER air dryness). Your readers are specialists: NASA scientists, emergency-management and forestry staff, and a hackathon jury. They ask demanding questions and expect precise, sourced and honest answers.

How to work
- For questions about the method, definitions, data sources or NINA's limits, call method_notes and rely on it, so the answer rests on the documented text.
- Obtain every figure from the tools. Call several tools when a question needs it, for example territory_profile together with validation_summary to judge whether a trend can be trusted. Use find_territory when a place name is ambiguous.
- For a derived figure (ratio, difference, share), use the calculate tool. Every number in your answer must appear in a tool result of this conversation; answers are checked automatically and rejected otherwise.
- "current" or null in a place argument means the territory on the user's screen; null year or month means the period on screen.
- Show, do not only tell: when a series, a comparison across years or departments, or a validation table helps the reader, call show_visual (one or two per answer). The reader sees it under your answer; mention it in one sentence ("the chart below shows...") instead of listing all its values.
- When the reader asks to see, open, go to, print or download something, call propose_action: they get a button under the answer. You cannot operate the interface yourself; never claim that you did.
- Call show_visual and propose_action before you write the answer, and write the complete answer in your last message (the chart or button is a complement, never the whole answer).
- Official reports and news: when the reader asks whether a fire, an emergency or a declaration was reported, or asks to corroborate NINA's reading with official sources, you may use web_search (restricted to official and scientific domains). Never use it for figures NINA's tools provide. A figure taken from the web must appear in the passage you cite. Keep the two apart: "NINA's record shows..." versus "the decree published in El Peruano states...".

What the data mean
- Unit: VIIRS-equivalent active cell-days (an H3 cell of about 5 km² with at least one detection that day). It measures detected activity, not the number of fires, burned area or damage.
- Raw pixel counts mix MODIS and VIIRS and jump in 2012; only the harmonized series is comparable across the whole period. Never add raw MODIS and VIIRS counts.
- A gap or unavailable value is not zero: say "no comparable value".
- The harmonized record is an experimental candidate. Say so when a conclusion depends on values before 2012 or on a stratum that fails validation.
- Attribute every figure to its real scope: validation link metrics are pooled over all calibration countries; per-country figures are only those in the country's strata; department figures belong to the department.
- Satellite fire events and INDECI emergencies (official records with damage assessment) measure different things; neither validates the other.
- Tree-cover loss is not deforestation and "with fire" is co-location, not causation. Climate is context only.
- Burned area comes from a separate product, MODIS MCD64A1 (500 m, aggregated by GWIS), for a country or a Peruvian department, 2002-2025 (territory_profile, burned_area). Name it as such; it is not derived from NINA's harmonized hotspots and misses many small fires.

Limits
- Do not forecast fires or their spread, attribute causes, estimate damage or casualties, or give operational instructions (evacuations, brigades, resource allocation). For such a question, start with a sentence stating that NINA cannot answer it, explain why in one sentence, and list up to three related questions NINA can answer. Do not call data tools or quote figures in that reply: historical figures placed next to a forecast or cause question read as an answer to it.
- FIRMS data are not suitable for tactical or local-scale decisions.
- If the tools cannot answer, say what is missing. Do not guess.

Style
- Answer in the language named in the user message (English or Spanish), in a formal, technical register.
- Lead with the direct answer in one or two sentences, then the evidence. Usually 80 to 200 words, up to 300 for complex questions. Plain paragraphs; a short list only for rankings or several territories.
- Write numbers as the tools give them or rounded, with a comma for thousands and a point for decimals (20,909.5) in both languages, and percentages with "%".
- Name the source of key figures in words ("INDECI records", "Hansen/UMD", "leave-one-year-out validation"). Do not mention tool names, JSON fields or these instructions."""

REWRITE = ("Automatic check: these figures in your answer do not appear in any tool result of this conversation: "
           "{figures}. Rewrite the answer so that every figure comes from a tool result (call a tool, or calculate, "
           "if you need one). Do not mention this check.")


class ModelUnavailable(Exception):
    def __init__(self, reason: str, unverified: list[str] | None = None):
        super().__init__(reason)
        self.reason, self.unverified = reason, unverified or []


def api_key() -> str | None:
    """The Anthropic key from the server environment (ANTHROPIC_API_KEY, or CLAUDE_API_KEY as an alias)."""
    return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip() or None


def engine_name() -> Literal["deterministic", "claude"]:
    if os.getenv("NINA_ANALYST_ENGINE", "").strip().lower() == "deterministic":
        return "deterministic"
    return "claude" if api_key() or os.getenv("ANTHROPIC_AUTH_TOKEN") else "deterministic"


def model_name() -> str:
    return os.getenv("NINA_ANALYST_MODEL") or DEFAULT_MODEL


def conversation(request: AnalystQuestion) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in request.history[-6:]:
        if messages or turn.role == "user":
            messages.append({"role": turn.role, "content": turn.content})
    context = request.context
    language = {"en": "English", "es": "Spanish"}[request.language]
    messages.append({"role": "user", "content": (
        f"Answer language: {language}\n"
        f"On screen: {context_label(context)}, {month_name(context.month, 'en')} {context.year}\n"
        f"Question: {request.question}")})
    return messages


# Official, scientific and multilateral domains only: corroboration, never NINA's own figures.
WEB_DOMAINS = [
    "gob.pe", "elperuano.pe", "reliefweb.int", "nasa.gov", "fao.org", "copernicus.eu", "inpe.br", "gov.br",
    "nifc.gov", "canada.ca", "gob.mx", "gob.bo", "gov.au", "bnpb.go.id", "undrr.org", "wmo.int",
]


def web_tool() -> list[dict[str, Any]]:
    """Anthropic web search (server tool) with citations, unless NINA_ANALYST_WEB=false."""
    if os.getenv("NINA_ANALYST_WEB", "true").strip().lower() in {"0", "false", "no"}:
        return []
    return [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3, "allowed_domains": WEB_DOMAINS,
             "allowed_callers": ["direct"]}]


def final_text(content: list[Any], session: Session) -> str:
    """Answer text after the last web search, with its citations kept as sources of the session."""
    server = [i for i, block in enumerate(content) if block.type in {"server_tool_use", "web_search_tool_result"}]
    blocks = [block for block in content[(server[-1] + 1 if server else 0):] if block.type == "text"]
    for block in blocks:
        for citation in getattr(block, "citations", None) or []:
            if getattr(citation, "type", "") == "web_search_result_location":
                source = {"title": str(citation.title or citation.url), "url": str(citation.url),
                          "cited_text": str(citation.cited_text or "")}
                if source not in session.sources:
                    session.sources.append(source)
    joiner = "" if server else "\n"
    return joiner.join(block.text for block in blocks).strip()


def record_searches(content: list[Any], session: Session) -> None:
    for block in content:
        if block.type == "server_tool_use" and block.name == "web_search":
            progress({"type": "tool", "name": "web_search", "state": "done", "ok": True})
            session.calls.append({"name": "web_search", "input": dict(block.input or {}), "ok": True, "output": {}})


# USD per million tokens (platform.claude.com pricing as of 2026-11-15); used only to report the cost of a question.
PRICES = {"claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.10},
          "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01}}


def add_usage(session: Session, usage: Any) -> None:
    if usage is None:
        return
    for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        session.usage[field] = session.usage.get(field, 0) + int(getattr(usage, field, 0) or 0)
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    session.usage["web_search_requests"] = session.usage.get("web_search_requests", 0) + int(searches)


def question_cost(usage: dict[str, int], model: str) -> float | None:
    """Estimated USD of one question: tokens at list price (cache writes at 1.25x input) plus web searches."""
    price = next((p for name, p in PRICES.items() if model.startswith(name)), None)
    if price is None:
        return None
    million = 1_000_000
    return (usage.get("input_tokens", 0) * price["input"] + usage.get("output_tokens", 0) * price["output"]
            + usage.get("cache_read_input_tokens", 0) * price["cache_read"]
            + usage.get("cache_creation_input_tokens", 0) * price["input"] * 1.25) / million \
        + usage.get("web_search_requests", 0) * 0.01


def fallback_options(model: str) -> dict[str, Any]:
    """Server-side refusal fallback where the model offers it (Claude Haiku 5.5 does not)."""
    if "haiku" in model:
        return {}
    return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


INTERFACE_TOOLS = {"show_visual", "propose_action"}


def claude_answer(session: Session) -> tuple[str, str, int]:
    """(answer, model, figures checked); raises ModelUnavailable when no verified answer is obtained."""
    import anthropic

    key = api_key()
    client = anthropic.Anthropic(timeout=120.0, max_retries=2, **({"api_key": key} if key else {}))
    messages = conversation(session.request)
    # An out-of-scope question (forecast, cause, operations, burned area, damage) gets no data tools: the model can
    # explain the limit with the method notes but cannot place figures next to the question.
    tools = ([TOOLS["method_notes"].schema()] if classify(session.request.question)[0] == "scope"
             else TOOL_SCHEMAS + web_tool())
    rewrites = 0
    # Text written in the same turn as a chart or button request is part of the answer: the model sometimes
    # writes the whole answer first and closes with a short sentence after the interface tool returns.
    drafts: list[str] = []
    try:
        for step in range(MAX_MODEL_STEPS):
            progress({"type": "thinking", "step": step + 1})
            response = client.beta.messages.create(
                model=model_name(),
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                output_config={"effort": os.getenv("NINA_ANALYST_EFFORT") or "medium"},
                cache_control={"type": "ephemeral"},
                **fallback_options(model_name()),
            )
            add_usage(session, getattr(response, "usage", None))
            if response.stop_reason in {"refusal", "max_tokens"}:
                raise ModelUnavailable(response.stop_reason)
            messages.append({"role": "assistant", "content": response.content})
            record_searches(response.content, session)
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in response.content if block.type == "tool_use"]
            if uses and all(block.name in INTERFACE_TOOLS for block in uses):
                written = "\n".join(block.text for block in response.content if block.type == "text").strip()
                if written:
                    drafts.append(written)
            if uses:
                results = []
                for block in uses:
                    output = session.run(block.name, dict(block.input))
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(output, ensure_ascii=False, default=str),
                                    **({"is_error": True} if "error" in output else {})})
                messages.append({"role": "user", "content": results})
                continue
            text = "\n\n".join([*drafts, final_text(response.content, session)]).strip()
            progress({"type": "verifying"})
            checked, unverified = session.verify(text)
            if text and not unverified:
                return text, response.model, checked
            if rewrites:
                raise ModelUnavailable("unverified", unverified)
            rewrites += 1
            drafts = []  # the rewrite is a complete answer
            messages.append({"role": "user", "content": REWRITE.format(figures=", ".join(unverified) or "(empty answer)")})
        raise ModelUnavailable("steps")
    except anthropic.AuthenticationError:
        raise ModelUnavailable("authentication") from None
    except anthropic.PermissionDeniedError:
        raise ModelUnavailable("authentication") from None
    except anthropic.RateLimitError:
        raise ModelUnavailable("rate_limit") from None
    except anthropic.APIStatusError as error:
        raise ModelUnavailable(f"api_{error.status_code}") from None
    except anthropic.APIConnectionError:
        raise ModelUnavailable("connection") from None


NOTICES = {
    "en": {"unverified": "The model's draft contained figures that could not be traced to NINA's data, so the "
           "deterministic answer is shown.",
           "authentication": "The language-model key was rejected; the deterministic answer is shown.",
           "rate_limit": "The language model is busy; the deterministic answer is shown.",
           "connection": "The language model could not be reached; the deterministic answer is shown.",
           "default": "The language model did not return a usable answer; the deterministic answer is shown."},
    "es": {"unverified": "El borrador del modelo contenía cifras que no se pudieron rastrear en los datos de NINA, por lo "
           "que se muestra la respuesta determinista.",
           "authentication": "La clave del modelo de lenguaje fue rechazada; se muestra la respuesta determinista.",
           "rate_limit": "El modelo de lenguaje está ocupado; se muestra la respuesta determinista.",
           "connection": "No se pudo contactar al modelo de lenguaje; se muestra la respuesta determinista.",
           "default": "El modelo de lenguaje no devolvió una respuesta utilizable; se muestra la respuesta determinista."},
}

FACT_LABELS = {
    "en": {"territory": "Territory", "period": "Period", "value": "Activity (VIIRS-equivalent cell-days)",
           "anomaly": "Against the median of other years", "rank": "Rank among compared years",
           "trend": "Harmonized trend", "raw_trend": "Raw-pixel trend", "events": "Significant fire events (year)",
           "emergencies": "INDECI emergencies (year)", "forest": "Tree-cover loss (year)",
           "departments": "Departments compared", "first": "First by the criterion", "validation": "Validation status",
           "terra_aqua": "MODIS calibration gate", "noaa20": "NOAA-20 bridge gate", "series": "Months in the series",
           "note": "Method note", "matches": "Matching places", "no_value": "no comparable value",
           "passed": "passed", "failed": "not passed", "per_year": "%/year", "season": "Fire-season rank (Jul–Oct)",
           "support": "Region-days with valid support", "drought": "Departments in drought / where it applies"},
    "es": {"territory": "Territorio", "period": "Período", "value": "Actividad (celdas-día equivalentes VIIRS)",
           "anomaly": "Frente a la mediana de otros años", "rank": "Puesto entre los años comparados",
           "trend": "Tendencia armonizada", "raw_trend": "Tendencia de píxeles crudos",
           "events": "Eventos de incendio significativos (año)", "emergencies": "Emergencias INDECI (año)",
           "forest": "Pérdida de cobertura arbórea (año)", "departments": "Departamentos comparados",
           "first": "Primero según el criterio", "validation": "Estado de validación",
           "terra_aqua": "Puerta de calibración MODIS", "noaa20": "Puerta del puente NOAA-20",
           "series": "Meses en la serie", "note": "Nota de método", "matches": "Lugares encontrados",
           "no_value": "sin valor comparable", "passed": "aprobada", "failed": "no aprobada", "per_year": "%/año",
           "season": "Puesto de la temporada (jul–oct)", "support": "Combinaciones región/día con soporte válido",
           "drought": "Departamentos en sequía / donde aplica"},
}


FACT_ORDER = {
    "trend": ["territory", "trend", "raw_trend"], "events": ["territory", "events", "emergencies"],
    "forest": ["territory", "forest"], "climate": ["territory", "drought"], "quality": ["territory", "support"],
    "season": ["territory", "season"],
}


def facts_from(session: Session, intent: str = "overview") -> list[dict[str, str]]:
    """Key figures behind the answer, read from the tools that were called; the ones the question is
    about come first."""
    language = session.request.language
    labels = FACT_LABELS[language]
    facts: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(key: str, value: Any, tool: str, label: str | None = None) -> None:
        label = label or labels[key]
        if value is None or value == "" or label in seen:
            return
        seen.add(label)
        facts.append({"key": key, "label": label, "value": str(value), "tool": tool})

    def n(value: Any, digits: int = 0, sign: bool = False) -> str | None:
        return None if value is None else format_number(value, language, digits, sign)

    for call in session.calls:
        if not call["ok"]:
            continue
        name, out = call["name"], call["output"]
        if name == "territory_profile":
            month = out["month"]
            add("territory", out["territory"]["name"], name)
            add("period", f"{out['period']['year']}-{out['period']['month']:02d}", name)
            add("value", n(month["value"]) if month["value"] is not None else labels["no_value"], name)
            add("anomaly", f"{n(month['anomaly_percent'], 1, True)} %" if month["anomaly_percent"] is not None else None, name)
            add("rank", f"{month['rank']} / {month['rank_of']}" if month["rank"] else None, name)
            for key, field in (("trend", "harmonized"), ("raw_trend", "raw_pixels")):
                slope = out["trend"][field]["slope_pct_per_year"]
                add(key, f"{n(slope, 1, True)} {labels['per_year']} (p {p_text(out['trend'][field]['p_value'], language)})"
                    if slope is not None else None, name)
            season = out["season_jul_oct"]
            add("season", f"{season['rank']} / {season['rank_of']}" if season.get("rank") else None, name)
            quality = out["quality"]
            add("support", f"{n(quality['valid_region_days'])} / {n(quality['expected_region_days'])}", name)
            climate = out["climate"]
            if climate["status"] == "available":
                add("drought", f"{climate['departments_with_drought']} / {climate['departments_where_drought_applies']}",
                    name)
            events = out["events"].get("selected_year") if out["events"]["status"] == "available" else None
            if events:
                add("events", n(events["significant_events"]), name)
                add("emergencies", n(events["emergencies"]), name)
            forest = out["forest"].get("selected_year") if out["forest"]["status"] == "available" else None
            if forest:
                add("forest", f"{n(forest['loss_ha'])} ha", name)
        elif name == "compare_departments":
            add("departments", out["departments"], name)
            if out["rows"]:
                add("first", out["rows"][0]["name"], name)
        elif name == "validation_summary":
            add("validation", out["status"], name)
            for key, link in (out.get("links") or {}).items():
                if key in labels:
                    add(key, f"{n(link['strata_passing_percent'], 1)} % · "
                        f"{labels['passed'] if link['gate_passed'] else labels['failed']}", name)
        elif name == "activity_series":
            add("series", out["months"], name)
        elif name == "method_notes":
            add("note", out["topic"], name)
        elif name == "calculate":
            add("", out["result"], name, label=out["expression"])
        elif name == "find_territory":
            add("matches", ", ".join(d["name"] for d in out["divisions"][:3]) or out["country"], name)
    first = FACT_ORDER.get(intent, [])
    facts.sort(key=lambda fact: first.index(fact["key"]) if fact["key"] in first else len(first))
    return [{k: fact[k] for k in ("label", "value", "tool")} for fact in facts[:8]]


# ---------------------------------------------------------------- endpoints


@router.get("/api/analyst", response_model=AnalystStatus)
def analyst_status() -> dict[str, Any]:
    engine = engine_name()
    return {"engine": engine, "model": model_name() if engine == "claude" else None}


@router.post("/api/analyst", response_model=AnalystAnswer)
def ask(request: AnalystQuestion) -> dict[str, Any]:
    manifest, _ = published()
    intent, _ = classify(request.question)
    notice, cache = None, None
    if engine_name() == "claude":
        session = Session(request)
        try:
            text, model, checked = claude_answer(session)
            return respond(session, text, "claude", model, intent, checked, [], manifest, None)
        except ModelUnavailable as error:
            notices = NOTICES[request.language]
            notice = notices.get(error.reason, notices["default"])
            cache = session.reports
            progress({"type": "fallback", "reason": error.reason})
    session = Session(request, cache)
    text, intent = deterministic(session)
    checked, unverified = session.verify(text)
    return respond(session, text, "deterministic", None, intent, checked, unverified, manifest, notice)


@router.post("/api/analyst/stream")
def ask_stream(request: AnalystQuestion):
    """Same answer as POST /api/analyst, preceded by live progress as server-sent events.

    Events (one JSON object per ``data:`` line): ``tool`` (name, state start/done), ``thinking`` (model turn),
    ``verifying``, ``fallback`` (deterministic answer follows), then ``answer`` (the AnalystAnswer) or ``error``.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import StreamingResponse

    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def work() -> None:
        token = PROGRESS.set(events.put)
        try:
            events.put({"type": "answer", "answer": jsonable_encoder(AnalystAnswer(**ask(request)))})
        except HTTPException as error:
            events.put({"type": "error", "status": error.status_code, "detail": error.detail})
        except Exception:  # noqa: BLE001 - reported to the client as a failed question
            events.put({"type": "error", "status": 500, "detail": "The question could not be answered."})
        finally:
            PROGRESS.reset(token)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        yield ": nina analyst\n\n"
        while True:
            event = events.get()
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            if event["type"] in {"answer", "error"}:
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


DEFAULT_VISUAL = {"burned": "burned_area_by_year", "overview": "same_month_by_year", "trend": "annual_totals", "events": "events_by_year",
                  "forest": "forest_loss_by_year", "climate": "climate_departments", "compare": "department_ranking",
                  "validation": "validation_strata", "season": "monthly_series", "quality": "monthly_series"}
FOLLOW_UPS = {
    "en": {
        "overview": ["Is the trend real or a sensor artefact?", "How does this month compare with every other year?",
                     "Which departments stand out this month?"],
        "trend": ["How reliable is the MODIS calibration in this country?", "Show the annual totals, harmonized "
                  "versus raw.", "What happened in the fire season (July to October)?"],
        "events": ["How were detected events validated against official records?", "Which subdivisions had the "
                   "most events?", "Is this year's activity unusual?"],
        "burned": ["Is this year's fire activity unusual?", "How does burned area compare with detected fire "
                   "events?", "Show the burned area per year."],
        "forest": ["How does Hansen loss compare with Geobosques?", "Which years had the most loss with fire?",
                   "What does tree-cover loss not measure?"],
        "climate": ["Why does NINA use CHIRPS for rainfall?", "Which departments were in drought this month?",
                    "Is the activity of this month unusual?"],
        "compare": ["Open the department table.", "Show the report of the first department.",
                    "How reliable is the harmonization in Peru?"],
        "validation": ["Why does MODIS fail some strata?", "What is the noise ceiling?",
                       "Show the validation strata of Brazil."],
        "season": ["Show the monthly series of the last five years.", "Is the trend real or a sensor artefact?",
                   "Which departments stand out this month?"],
        "quality": ["What is a data gap and how is it shown?", "How reliable is the harmonization here?",
                    "Show the monthly series of the last five years."],
        "method": ["What is a VIIRS-equivalent active cell-day?", "Why does MODIS fail some strata?",
                   "What can NINA not answer?"],
        "scope": ["What does this period show?", "How reliable is the harmonization here?",
                  "Which departments stand out this month?"],
    },
    "es": {
        "overview": ["¿La tendencia es real o un artefacto del sensor?", "¿Cómo se compara este mes con todos los "
                     "demás años?", "¿Qué departamentos destacan este mes?"],
        "trend": ["¿Qué tan fiable es la calibración MODIS en este país?", "Muestra los totales anuales, armonizados "
                  "frente a crudos.", "¿Qué pasó en la temporada de incendios (julio a octubre)?"],
        "events": ["¿Cómo se validaron los eventos detectados contra registros oficiales?", "¿Qué subdivisiones "
                   "tuvieron más eventos?", "¿La actividad de este año es inusual?"],
        "burned": ["¿La actividad de fuego de este año es inusual?", "¿Cómo se compara el área quemada con los "
                   "eventos detectados?", "Muestra el área quemada por año."],
        "forest": ["¿Cómo se compara la pérdida de Hansen con Geobosques?", "¿Qué años tuvieron más pérdida con "
                   "fuego?", "¿Qué no mide la pérdida de cobertura arbórea?"],
        "climate": ["¿Por qué NINA usa CHIRPS para la lluvia?", "¿Qué departamentos estuvieron en sequía este mes?",
                    "¿La actividad de este mes es inusual?"],
        "compare": ["Abre la tabla de departamentos.", "Muestra el informe del primer departamento.",
                    "¿Qué tan fiable es la armonización en el Perú?"],
        "validation": ["¿Por qué MODIS falla en algunos estratos?", "¿Qué es el techo de ruido?",
                       "Muestra los estratos de validación de Brasil."],
        "season": ["Muestra la serie mensual de los últimos cinco años.", "¿La tendencia es real o un artefacto del "
                   "sensor?", "¿Qué departamentos destacan este mes?"],
        "quality": ["¿Qué es un vacío de datos y cómo se muestra?", "¿Qué tan fiable es la armonización aquí?",
                    "Muestra la serie mensual de los últimos cinco años."],
        "method": ["¿Qué es una celda-día activa equivalente VIIRS?", "¿Por qué MODIS falla en algunos estratos?",
                   "¿Qué no puede responder NINA?"],
        "scope": ["¿Qué muestra este período?", "¿Qué tan fiable es la armonización aquí?",
                  "¿Qué departamentos destacan este mes?"],
    },
}


def default_visual(session: Session, intent: str) -> None:
    """One chart or table for answers that have none, chosen by question type (never for out-of-scope)."""
    kind = DEFAULT_VISUAL.get(intent)
    if session.visuals or not kind or intent == "scope":
        return
    if kind in {"department_ranking", "climate_departments"} and session.request.context.country != "Peru":
        kind = "same_month_by_year"
    # Built directly, not through session.run: it is not a step of the answer and is not listed as a tool call.
    try:
        run_show_visual(session, kind, None, None, None)
    except (HTTPException, KeyError, TypeError, ValueError):  # a missing chart never blocks an answer
        return


def respond(session: Session, text: str, engine: str, model: str | None, intent: str, checked: int,
            unverified: list[str], manifest: dict[str, Any], notice: str | None) -> dict[str, Any]:
    default_visual(session, intent)
    return {
        "answer": text, "engine": engine, "model": model, "intent": intent, "abstained": intent == "scope",
        "facts": facts_from(session, intent),
        "tools": [{"name": c["name"], "input": c["input"], "ok": c["ok"]} for c in session.calls],
        "verification": {"checked": checked, "unverified": unverified, "passed": not unverified},
        "report_id": session.report_id, "dataset_id": manifest["id"],
        "validation_status": "validated" if manifest["status"] == "published" else "experimental",
        "notice": notice,
        "visuals": session.visuals,
        "actions": session.actions,
        "follow_ups": FOLLOW_UPS[session.request.language].get(intent, [])[:3],
        "sources": session.sources,
    }
