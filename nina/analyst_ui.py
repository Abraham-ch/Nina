"""Charts, tables and interface actions of the analytical assistant.

The model chooses what to show; the numbers of every chart and table are built here from NINA's own results
(territorial report, department table, validation manifest), so they are correct by construction and never
typed by the model. Pure functions: no database access and no model calls.
"""

from __future__ import annotations

import statistics
from typing import Any, Literal

from pydantic import BaseModel, Field

MAX_POINTS = 120
MAX_ROWS = 30

VISUAL_KINDS = {
    "monthly_series": "line chart of the monthly harmonized activity of one territory over the last five years",
    "same_month_by_year": "bars of one calendar month across all years, with the median of the other years",
    "annual_totals": "harmonized versus raw-pixel annual totals as an index (median year = 100); shows the 2012 "
    "jump of raw counts that the harmonization removes",
    "events_by_year": "satellite fire events per year next to registered emergencies or incidents",
    "forest_loss_by_year": "Hansen/UMD tree-cover loss per year, total and co-located with fire (Peru)",
    "burned_area_by_year": "MODIS MCD64A1 burned area per year (GWIS), for a country or a Peruvian department",
    "department_ranking": "table of Peru's departments for one month (activity, anomaly, rank, events, emergencies)",
    "validation_strata": "table of the validation strata (biomes) of one country: MODIS bias and Spearman, the "
    "NOAA-20 noise ceiling and the status",
    "climate_departments": "table of rainfall and air-dryness anomalies and the drought flag by department (Peru)",
}
ACTION_KINDS = {
    "show_on_map": "select the territory and period in the atlas",
    "open_calendar": "select the territory and period and open the activity calendar",
    "open_priorities": "open the table of Peru's departments for the period",
    "open_report": "open the printable territorial report",
    "download_data": "download the report package (HTML, JSON and CSV tables with the FIRMS citation)",
}

TEXT = {
    "en": {
        "monthly_series": "Monthly activity, {place}",
        "same_month_by_year": "{month_name} in every year, {place}",
        "annual_totals": "Harmonized versus raw annual totals, {place}",
        "events_by_year": "Fire events and registered cases per year, {place}",
        "forest_loss_by_year": "Tree-cover loss per year, {place}",
        "burned_area_by_year": "Burned area per year (MODIS MCD64A1), {place}",
        "burned": "Burned area (ha)", "source_burned": "MODIS MCD64A1 c6.1 burned area aggregated by GWIS (JRC/Copernicus), CC BY 4.0; independent of NINA's hotspots",
        "department_ranking": "Peru's departments, {month_name} {year}",
        "validation_strata": "Validation strata of {country}",
        "climate_departments": "Climate context by department, {month_name} {year}",
        "harmonized": "Harmonized activity", "raw": "Raw pixels (MODIS + VIIRS)", "events": "Significant fire events",
        "loss": "Tree-cover loss (ha)", "loss_fire": "Loss co-located with fire (ha)", "median": "Median of other years",
        "unit": "VIIRS-equivalent active cell-days", "index": "Index, median year = 100",
        "gaps": "A break in the line is a month without a comparable value, never zero.",
        "index_note": "Raw pixel counts jump in 2012 when VIIRS (375 m) joins MODIS (1 km); the harmonized series "
        "keeps one unit for the whole period.",
        "col_department": "Department", "col_activity": "Activity", "col_anomaly": "vs median (%)",
        "col_rank": "Rank of month", "col_events": "Significant events", "col_emergencies": "INDECI emergencies",
        "col_biome": "Biome", "col_bias": "MODIS bias (%)", "col_rho": "MODIS Spearman",
        "col_ceiling": "NOAA-20 Spearman (ceiling)", "col_status": "Status", "col_rain": "Rainfall anomaly (z)",
        "col_vpd": "Air dryness anomaly (z)", "col_drought": "Drought", "col_source": "Rainfall source",
        "passed": "passed", "failed": "not passed", "below": "below noise ceiling", "not_evaluable": "not evaluable",
        "yes": "yes", "no": "no", "na": "not applicable",
        "source_report": "NINA territorial report (harmonized record, experimental candidate)",
        "source_priority": "NINA department table; each indicator is separate, there is no composite score",
        "source_validation": "Leave-one-year-out validation of the harmonization",
        "source_climate": "CHIRPS v2.0 rainfall and NASA POWER air dryness, anomalies against 2002–2024",
        "source_forest": "Hansen/UMD Global Forest Change; loss is not deforestation and co-location is not cause",
        "strata_note": "A stratum below the noise ceiling is one where NOAA-20, the same instrument as the S-NPP "
        "reference, cannot order the months either (ADR 0006).",
    },
    "es": {
        "monthly_series": "Actividad mensual, {place}",
        "same_month_by_year": "{month_name} de cada año, {place}",
        "annual_totals": "Totales anuales armonizados frente a crudos, {place}",
        "events_by_year": "Eventos de incendio y casos registrados por año, {place}",
        "forest_loss_by_year": "Pérdida de cobertura arbórea por año, {place}",
        "burned_area_by_year": "Área quemada por año (MODIS MCD64A1), {place}",
        "burned": "Área quemada (ha)", "source_burned": "Área quemada MODIS MCD64A1 c6.1 agregada por GWIS (JRC/Copernicus), CC BY 4.0; independiente de los focos de NINA",
        "department_ranking": "Departamentos del Perú, {month_name} de {year}",
        "validation_strata": "Estratos de validación de {country}",
        "climate_departments": "Contexto climático por departamento, {month_name} de {year}",
        "harmonized": "Actividad armonizada", "raw": "Píxeles crudos (MODIS + VIIRS)",
        "events": "Eventos de incendio significativos", "loss": "Pérdida de cobertura arbórea (ha)",
        "loss_fire": "Pérdida coincidente con fuego (ha)", "median": "Mediana de los otros años",
        "unit": "celdas-día activas equivalentes VIIRS", "index": "Índice, año mediano = 100",
        "gaps": "Un corte en la línea es un mes sin valor comparable, nunca cero.",
        "index_note": "Los píxeles crudos saltan en 2012 cuando VIIRS (375 m) se suma a MODIS (1 km); la serie "
        "armonizada mantiene una sola unidad en todo el período.",
        "col_department": "Departamento", "col_activity": "Actividad", "col_anomaly": "vs mediana (%)",
        "col_rank": "Puesto del mes", "col_events": "Eventos significativos", "col_emergencies": "Emergencias INDECI",
        "col_biome": "Bioma", "col_bias": "Sesgo MODIS (%)", "col_rho": "Spearman MODIS",
        "col_ceiling": "Spearman NOAA-20 (techo)", "col_status": "Estado", "col_rain": "Anomalía de lluvia (z)",
        "col_vpd": "Anomalía de sequedad del aire (z)", "col_drought": "Sequía", "col_source": "Fuente de lluvia",
        "passed": "aprobado", "failed": "no aprobado", "below": "bajo el techo de ruido", "not_evaluable": "no evaluable",
        "yes": "sí", "no": "no", "na": "no aplica",
        "source_report": "Informe territorial de NINA (registro armonizado, candidato experimental)",
        "source_priority": "Tabla de departamentos de NINA; cada indicador es separado, no hay puntaje compuesto",
        "source_validation": "Validación dejando un año fuera de la armonización",
        "source_climate": "Lluvia CHIRPS v2.0 y sequedad del aire NASA POWER, anomalías respecto de 2002–2024",
        "source_forest": "Hansen/UMD Global Forest Change; pérdida no es deforestación y coincidir no es causar",
        "strata_note": "Un estrato bajo el techo de ruido es uno donde NOAA-20, el mismo instrumento que la "
        "referencia S-NPP, tampoco puede ordenar los meses (ADR 0006).",
    },
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
}


class VisualSeries(BaseModel):
    name: str
    values: list[float | None]


class AnalystVisual(BaseModel):
    id: str
    kind: str
    type: Literal["chart", "table"]
    chart: Literal["line", "bar"] | None = None
    title: str
    unit: str | None = None
    categories: list[str] = Field(default_factory=list)
    series: list[VisualSeries] = Field(default_factory=list)
    reference_value: float | None = None
    reference_label: str | None = None
    highlight: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str | float | None]] = Field(default_factory=list)
    note: str | None = None
    source: str


class AnalystAction(BaseModel):
    id: str
    kind: Literal["show_on_map", "open_calendar", "open_priorities", "open_report", "download_data"]
    label: str
    country: str | None = None
    department: str | None = Field(default=None, description="Peruvian department name, when the target is one")
    year: int | None = None
    month: int | None = None
    report_id: str | None = None


def r(value: Any, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def month_label(month: int, language: str) -> str:
    return MONTHS[language][month - 1]


def place_of(report: dict[str, Any]) -> str:
    return str(report["territory"].get("name") or report["territory"].get("country") or "")


def visual(identifier: str, kind: str, language: str, title_fields: dict[str, Any], **fields: Any) -> dict[str, Any]:
    t = TEXT[language]
    title = t[kind].format(**title_fields)
    return AnalystVisual(id=identifier, kind=kind, title=title, **fields).model_dump()


def monthly_series(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any]:
    t = TEXT[language]
    year, month = report["period"]["year"], report["period"]["month"]
    rows = [m for m in report["sections"]["current"].get("calendar") or [] if year - 4 <= m["year"] <= year]
    rows = rows[-MAX_POINTS:]
    return visual(identifier, "monthly_series", language, {"place": place_of(report)}, type="chart", chart="line",
                  unit=t["unit"], categories=[f"{m['year']}-{m['month']:02d}" for m in rows],
                  series=[VisualSeries(name=t["harmonized"], values=[r(m["value"]) for m in rows])],
                  highlight=f"{year}-{month:02d}", note=t["gaps"], source=t["source_report"])


def same_month_by_year(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any]:
    t = TEXT[language]
    year, month = report["period"]["year"], report["period"]["month"]
    rows = [m for m in report["sections"]["current"].get("calendar") or [] if m["month"] == month]
    median = report["sections"]["current"]["month"].get("historical_median")
    return visual(identifier, "same_month_by_year", language,
                  {"place": place_of(report), "month_name": month_label(month, language).capitalize()},
                  type="chart", chart="bar", unit=t["unit"], categories=[str(m["year"]) for m in rows],
                  series=[VisualSeries(name=t["harmonized"], values=[r(m["value"]) for m in rows])],
                  reference_value=r(median), reference_label=t["median"] if median is not None else None,
                  highlight=str(year), note=t["gaps"], source=t["source_report"])


def index(values: list[float]) -> list[float | None]:
    positive = [v for v in values if v > 0]
    if not positive:
        return [None for _ in values]
    middle = statistics.median(positive)
    return [r(100 * v / middle) for v in values]


def annual_totals(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any]:
    t = TEXT[language]
    rows = report["sections"]["history"].get("annual") or []
    return visual(identifier, "annual_totals", language, {"place": place_of(report)}, type="chart", chart="line",
                  unit=t["index"], categories=[str(a["year"]) for a in rows],
                  series=[VisualSeries(name=t["harmonized"], values=index([a["harmonized"] for a in rows])),
                          VisualSeries(name=t["raw"], values=index([a["raw_pixels"] for a in rows]))],
                  highlight=str(report["period"]["year"]), note=t["index_note"], source=t["source_report"])


def events_by_year(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any] | None:
    t = TEXT[language]
    events = report["sections"]["events"]
    if events.get("status") != "available":
        return None
    rows = events["by_year"]
    series = [VisualSeries(name=t["events"], values=[r(row["significant_events"], 0) for row in rows])]
    if any(row.get("emergencies") is not None for row in rows):
        label = events.get("emergencies_label") or t["col_emergencies"]
        series.append(VisualSeries(name=str(label), values=[r(row.get("emergencies"), 0) for row in rows]))
    return visual(identifier, "events_by_year", language, {"place": place_of(report)}, type="chart", chart="bar",
                  categories=[str(row["year"]) for row in rows], series=series,
                  highlight=str(report["period"]["year"]), note=events.get("rule"), source=t["source_report"])


def forest_loss_by_year(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any] | None:
    t = TEXT[language]
    forest = report["sections"]["forest"]
    if forest.get("status") != "available":
        return None
    rows = forest["by_year"]
    return visual(identifier, "forest_loss_by_year", language, {"place": place_of(report)}, type="chart",
                  chart="bar", unit="ha", categories=[str(row["year"]) for row in rows],
                  series=[VisualSeries(name=t["loss"], values=[r(row["loss_ha"], 0) for row in rows]),
                          VisualSeries(name=t["loss_fire"], values=[r(row["loss_ha_with_fire"], 0) for row in rows])],
                  highlight=str(report["period"]["year"]), source=t["source_forest"])


def burned_area_by_year(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any] | None:
    t = TEXT[language]
    burned = report["sections"].get("burned_area") or {}
    if burned.get("status") != "available":
        return None
    rows = burned["by_year"]
    return visual(identifier, "burned_area_by_year", language, {"place": burned["unit"]}, type="chart", chart="bar",
                  unit="ha", categories=[str(r["year"]) for r in rows],
                  series=[VisualSeries(name=t["burned"], values=[r(row["burned_ha"], 0) for row in rows])],
                  highlight=str(report["period"]["year"]), note=burned.get("note"), source=t["source_burned"])


def department_ranking(identifier: str, table: dict[str, Any], rows: list[dict[str, Any]], language: str,
                       year: int, month: int) -> dict[str, Any]:
    t = TEXT[language]
    columns = [t["col_department"], t["col_activity"], t["col_anomaly"], t["col_rank"], t["col_events"],
               t["col_emergencies"]]
    body = [[row["name"], r(row.get("month_value")), r(row.get("month_anomaly")),
             f"{row['month_rank']} / {row['month_rank_of']}" if row.get("month_rank") else None,
             r(row.get("significant_events"), 0), r(row.get("emergencies"), 0)] for row in rows[:MAX_ROWS]]
    return visual(identifier, "department_ranking", language,
                  {"month_name": month_label(month, language), "year": year}, type="table", columns=columns,
                  rows=body, unit=t["unit"], source=t["source_priority"])


def validation_strata(identifier: str, validation: dict[str, Any], country: str, biomes: dict[int, str],
                      language: str) -> dict[str, Any] | None:
    t = TEXT[language]
    modis = [s for s in validation.get("terra_aqua", {}).get("strata", []) if s["country"] == country]
    if not modis:
        return None
    ceiling = {s["biome"]: s.get("spearman") for s in validation.get("noaa20", {}).get("strata", [])
               if s["country"] == country and s.get("evaluable")}

    def status(s: dict[str, Any]) -> str:
        if s.get("below_noise_ceiling"):
            return t["below"]
        if not s.get("evaluable"):
            return t["not_evaluable"]
        return t["passed"] if s.get("passed") else t["failed"]

    body = [[biomes.get(s["biome"], str(s["biome"])),
             None if s.get("relative_bias") is None else r(100 * s["relative_bias"]),
             r(s.get("spearman"), 2), r(ceiling.get(s["biome"]), 2), status(s)]
            for s in sorted(modis, key=lambda s: s["biome"])]
    return visual(identifier, "validation_strata", language, {"country": country}, type="table",
                  columns=[t["col_biome"], t["col_bias"], t["col_rho"], t["col_ceiling"], t["col_status"]],
                  rows=body, note=t["strata_note"], source=t["source_validation"])


def climate_departments(identifier: str, report: dict[str, Any], language: str) -> dict[str, Any] | None:
    t = TEXT[language]
    climate = report["sections"]["climate"]
    if climate.get("status") != "available":
        return None
    year, month = report["period"]["year"], report["period"]["month"]

    def drought(value: Any) -> str:
        return t["na"] if value is None else (t["yes"] if value else t["no"])

    body = [[str(row["department"]).title(), r(row.get("precip_z"), 2), r(row.get("vpd_z"), 2),
             drought(row.get("drought")), row.get("precip_source")] for row in climate["selected_month"][:MAX_ROWS]]
    return visual(identifier, "climate_departments", language,
                  {"month_name": month_label(month, language), "year": year}, type="table",
                  columns=[t["col_department"], t["col_rain"], t["col_vpd"], t["col_drought"], t["col_source"]],
                  rows=body, note=climate.get("note"), source=t["source_climate"])


def compact(spec: dict[str, Any]) -> dict[str, Any]:
    """What the model sees of a visual it requested: the same numbers, without styling."""
    out: dict[str, Any] = {"visual_id": spec["id"], "kind": spec["kind"], "title": spec["title"],
                           "shown_to_user": True}
    if spec["type"] == "chart":
        out["categories"] = spec["categories"][-60:]
        out["series"] = [{"name": s["name"], "values": s["values"][-60:]} for s in spec["series"]]
        if spec.get("reference_value") is not None:
            out["reference"] = {"label": spec["reference_label"], "value": spec["reference_value"]}
    else:
        out["columns"], out["rows"] = spec["columns"], spec["rows"]
    if spec.get("note"):
        out["note"] = spec["note"]
    return out
