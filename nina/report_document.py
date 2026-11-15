"""Printable HTML for the territorial report: A4, inline SVG charts, no external assets except the
NASA GIBS images served by NINA itself.

It only lays out facts already computed by ``nina.reports``; ratios shown in the cards are simple
divisions of those facts. Label density is controlled so that axis labels never overlap.
"""

from __future__ import annotations

import html
import math
from typing import Any

INK, MUTED, GRID = "#17212b", "#5b6776", "#e3e8ee"
FIRE, FIRE_DARK, RAW, BLUE = "#c2410c", "#7c2d12", "#94a3b8", "#2563eb"
BAND, MEDIAN = "#e2e8f0", "#475569"

LABELS = {
    "en": {
        "kicker": "NINA · Territorial fire evidence report",
        "experimental": "Experimental harmonized product · not an official document · not for tactical decisions",
        "card_month": "Selected month", "card_season": "Fire season (Jul–Oct)", "card_trend": "Real trend",
        "card_events": "Detected fires / recorded emergencies", "card_forest": "Tree-cover loss",
        "card_drought": "Drought (month)", "rank": "rank {r} of {n}", "per_year": "%/year",
        "raw_note": "raw series: {v} %/year (sensor artefact)", "no_trend": "no significant trend",
        "per_emergency": "{v} detected fires per recorded emergency", "no_emergency": "no INDECI record",
        "with_fire": "{v} % in areas with fire activity", "drought_yes": "Yes", "drought_no": "No",
        "drought_na": "Not applicable (dry month)", "precip_pct": "rainfall percentile {v}",
        "unit": "VIIRS-equivalent active cell-days", "na": "Not available", "days_so_far": "{d} valid days so far",
        "chart_profile": "This year against the normal range",
        "chart_profile_note": "Monthly activity. Band: 10th–90th percentile of the other years; dashed line: median.",
        "chart_calendar": "Activity calendar: anomaly against the median of the other years",
        "chart_calendar_note": "Each cell is a month; the outlined cell is the month analysed. Grey hatching: no comparable value (never zero).",
        "chart_trend": "The sensor change creates a false trend",
        "chart_trend_note": "Annual activity relative to the MODIS-era mean (2003–2011 = 100). Raw counts jump when VIIRS arrives in 2012; the harmonized series does not.",
        "legend_harmonized": "Harmonized (NINA)", "legend_raw": "Raw pixels (sensors mixed)",
        "legend_median": "Median", "legend_band": "Normal range (p10–p90)",
        "chart_events": "Detected fire events and recorded emergencies",
        "chart_events_note": "Significant events: at least 5 active cell-days (VIIRS era). Emergencies: INDECI/SINPAD records with damage assessment, not every fire.",
        "legend_events": "Detected fire events", "legend_emergencies": "INDECI emergencies",
        "chart_subdivisions": "By subdivision, {y}",
        "chart_forest": "Tree-cover loss and fire activity",
        "legend_with_fire": "In cells with fire activity", "legend_other": "Other loss",
        "method_break": "method change", "chart_climate": "Climatic conditions",
        "col_department": "Department", "col_precip": "Rainfall percentile", "col_vpd": "Air dryness (VPD z)",
        "col_drought": "Drought", "chart_imagery": "Seen from space (NASA GIBS, real imagery)",
        "before": "Before · {d}", "after": "Most active day · {d}",
        "imagery_note": "True colour with satellite thermal anomalies (red). Clouds or smoke may hide the ground; the yellow line is the territory.",
        "quality": "Quality and limitations", "sources": "Sources and reproducibility",
        "print": "Print / save as PDF",
        "q_support": "{v} of {e} region-days with valid data; {f} filled from NOAA-20; unvalidated share {u}.",
        "q_unit": "Unit: active H3 cells (~5 km²) per day on a VIIRS S-NPP-equivalent scale; not a count of fires or burned area.",
        "forest_definition": "Tree-cover loss (Hansen/UMD, canopy ≥ 30 % in 2000). 'In cells with fire activity': cell with satellite fire activity in the same or the previous year.",
        "forest_validation": "Peru totals 2001–2024 within 0.3–0.6 % of Global Forest Watch.",
        "forest_caveats": ["Tree-cover loss is not deforestation: it includes fire-killed forest and plantation harvest.",
                           "Loss in cells with fire shows co-location, not causation.",
                           "The Hansen method changed in 2011–2012: do not read a trend across that break."],
        "climate_source": "NASA POWER (MERRA-2, ~50 km), monthly anomalies against 2002–2024.",
        "climate_note": "Context only, not a cause. Drought: rainfall z ≤ −1 and air dryness (VPD) z ≥ +1; not applicable where the month is normally dry. Rainfall percentile: 0 = driest of the 23 reference years.",
        "typical_error": "Year-to-year error of the MODIS-era values: about ±10 % (median 6 % in validated strata).",
        "months_short": ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"],
        "months_long": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                        "October", "November", "December"],
        "type": {"country": "Country", "department": "Department", "province": "Province",
                 "district": "District", "polygon": "Custom area"},
    },
    "es": {
        "kicker": "NINA · Informe técnico territorial de actividad de fuego",
        "experimental": "Producto armonizado experimental · no es un documento oficial · no apto para decisiones tácticas",
        "card_month": "Mes analizado", "card_season": "Temporada de incendios (jul–oct)",
        "card_trend": "Tendencia real", "card_events": "Incendios detectados / emergencias registradas",
        "card_forest": "Pérdida de cobertura arbórea", "card_drought": "Sequía (mes)",
        "rank": "puesto {r} de {n}", "per_year": "%/año",
        "raw_note": "serie cruda: {v} %/año (artefacto del cambio de sensor)",
        "no_trend": "sin tendencia significativa",
        "per_emergency": "{v} incendios detectados por emergencia registrada", "no_emergency": "sin registro de INDECI",
        "with_fire": "{v} % en zonas con actividad de fuego", "drought_yes": "Sí", "drought_no": "No",
        "drought_na": "No aplica (mes seco)", "precip_pct": "percentil de lluvia {v}",
        "unit": "celdas-día activas equivalentes VIIRS", "na": "No disponible", "days_so_far": "{d} días válidos hasta ahora",
        "chart_profile": "Este año frente al rango normal",
        "chart_profile_note": "Actividad mensual. Banda: percentiles 10–90 de los demás años; línea discontinua: mediana.",
        "chart_calendar": "Calendario de actividad: anomalía respecto de la mediana de los demás años",
        "chart_calendar_note": "Cada celda es un mes; la celda marcada es el mes analizado. Trama gris: sin valor comparable (nunca es cero).",
        "chart_trend": "El cambio de sensor crea una tendencia falsa",
        "chart_trend_note": "Actividad anual respecto del promedio de la era MODIS (2003–2011 = 100). Los conteos crudos saltan cuando llega VIIRS en 2012; la serie armonizada no.",
        "legend_harmonized": "Armonizada (NINA)", "legend_raw": "Píxeles crudos (sensores mezclados)",
        "legend_median": "Mediana", "legend_band": "Rango normal (p10–p90)",
        "chart_events": "Incendios detectados y emergencias registradas",
        "chart_events_note": "Incendios significativos: al menos 5 celdas-día activas (era VIIRS). Emergencias: registros de INDECI/SINPAD con evaluación de daños, no todo incendio.",
        "legend_events": "Incendios detectados", "legend_emergencies": "Emergencias INDECI",
        "chart_subdivisions": "Por subdivisión, {y}",
        "chart_forest": "Pérdida de cobertura arbórea y actividad de fuego",
        "legend_with_fire": "En celdas con actividad de fuego", "legend_other": "Resto de la pérdida",
        "method_break": "cambio de método", "chart_climate": "Condiciones climáticas",
        "col_department": "Departamento", "col_precip": "Percentil de lluvia", "col_vpd": "Sequedad del aire (DPV z)",
        "col_drought": "Sequía", "chart_imagery": "Visto desde el espacio (NASA GIBS, imágenes reales)",
        "before": "Antes · {d}", "after": "Día de mayor actividad · {d}",
        "imagery_note": "Color verdadero con anomalías térmicas satelitales (rojo). Nubes o humo pueden ocultar el suelo; la línea amarilla es el territorio.",
        "quality": "Calidad y limitaciones", "sources": "Fuentes y reproducibilidad",
        "print": "Imprimir / guardar como PDF",
        "q_support": "{v} de {e} días-región con datos válidos; {f} completados con NOAA-20; proporción sin validar {u}.",
        "q_unit": "Unidad: celdas H3 activas (~5 km²) por día en escala equivalente a VIIRS S-NPP; no es número de incendios ni área quemada.",
        "forest_definition": "Pérdida de cobertura arbórea (Hansen/UMD, dosel ≥ 30 % en 2000). 'En celdas con actividad de fuego': celda con actividad de fuego satelital el mismo año o el anterior.",
        "forest_validation": "Totales del Perú 2001–2024 dentro de 0,3–0,6 % de Global Forest Watch.",
        "forest_caveats": ["La pérdida de cobertura arbórea no es deforestación: incluye bosque muerto por fuego y cosecha de plantaciones.",
                           "La pérdida en celdas con fuego indica coincidencia, no causa.",
                           "El método de Hansen cambió en 2011–2012: no leer una tendencia a través de ese quiebre."],
        "climate_source": "NASA POWER (MERRA-2, ~50 km), anomalías mensuales respecto de 2002–2024.",
        "climate_note": "Solo contexto, no causa. Sequía: lluvia z ≤ −1 y sequedad del aire (DPV) z ≥ +1; no aplica en meses normalmente secos. Percentil de lluvia: 0 = el más seco de los 23 años de referencia.",
        "typical_error": "Error interanual de los valores de la era MODIS: alrededor de ±10 % (mediana de 6 % en estratos validados).",
        "months_short": ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"],
        "months_long": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre",
                        "octubre", "noviembre", "diciembre"],
        "type": {"country": "País", "department": "Departamento", "province": "Provincia",
                 "district": "Distrito", "polygon": "Área seleccionada"},
    },
}

CSS = """
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font: 10pt/1.45 "Segoe UI", system-ui, -apple-system, sans-serif; color: #17212b; background: #fff;
       margin: 0 auto; max-width: 186mm; padding: 6mm 4mm; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 6mm;
         border-bottom: 3px solid #c2410c; padding-bottom: 3mm; }
.kicker { font-size: 8.5pt; letter-spacing: .04em; text-transform: uppercase; color: #5b6776; margin: 0; }
h1 { font-size: 22pt; line-height: 1.1; margin: 1mm 0 1mm; }
.subtitle { color: #5b6776; margin: 0; }
.badge { font-size: 7.5pt; color: #92400e; background: #fff7ed; border: 1px solid #fdba74; border-radius: 3px;
         padding: 1mm 2mm; max-width: 52mm; text-align: right; }
.headline { font-size: 13.5pt; line-height: 1.35; font-weight: 600; margin: 4mm 0; padding: 3mm 4mm;
            border-left: 5px solid #94a3b8; background: #f8fafc; }
.headline.record, .headline.above { border-color: #b2182b; background: #fef2f2; }
.headline.below { border-color: #2166ac; background: #eff6ff; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin: 0 0 4mm; }
.card { border: 1px solid #e3e8ee; border-radius: 4px; padding: 2.5mm 3mm; break-inside: avoid; }
.card h3 { font-size: 7.5pt; font-weight: 600; color: #5b6776; margin: 0 0 1mm; text-transform: uppercase; letter-spacing: .03em; }
.card .big { font-size: 17pt; font-weight: 700; line-height: 1.15; }
.card .small { font-size: 8.5pt; color: #5b6776; margin-top: .5mm; }
.chip { display: inline-block; font-size: 9pt; font-weight: 700; padding: 0 1.5mm; border-radius: 3px; color: #fff; vertical-align: 3px; }
.chip.up { background: #b2182b; } .chip.down { background: #2166ac; } .chip.flat { background: #64748b; }
section { break-inside: avoid; margin: 0 0 4mm; }
h2 { font-size: 11.5pt; margin: 3mm 0 1mm; }
.note { font-size: 8pt; color: #5b6776; margin: 0 0 1mm; }
svg { display: block; width: 100%; height: auto; }
svg text { font-family: "Segoe UI", system-ui, sans-serif; fill: #5b6776; }
.legend { font-size: 8pt; color: #5b6776; display: flex; flex-wrap: wrap; gap: 4mm; margin: 1mm 0 0; }
.legend i { display: inline-block; width: 10px; height: 10px; margin-right: 1.5mm; vertical-align: -1px; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; }
th, td { border-bottom: 1px solid #e3e8ee; padding: 1.2mm 1.5mm; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { color: #5b6776; font-weight: 600; font-size: 8pt; }
.page-break { break-before: page; }
.images { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; }
.images figure { margin: 0; }
.frame { position: relative; }
.frame img { width: 100%; display: block; border-radius: 3px; background: #e2e8f0; min-height: 40mm; }
.frame svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.images figcaption { font-size: 8pt; color: #5b6776; margin-top: 1mm; }
.box { border: 1px solid #e3e8ee; border-radius: 4px; padding: 2mm 3mm; font-size: 8.5pt; color: #374151; }
.box ul { margin: 1mm 0 0 4mm; padding: 0; }
footer { margin-top: 4mm; font-size: 7.5pt; color: #5b6776; border-top: 1px solid #e3e8ee; padding-top: 2mm; }
.toolbar { text-align: right; margin: 0 0 3mm; }
.toolbar button { font: inherit; padding: 1.5mm 4mm; border: 1px solid #c2410c; background: #c2410c; color: #fff;
                  border-radius: 3px; cursor: pointer; }
@media print { .toolbar { display: none; } body { padding: 0; } }
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def format_number(value: Any, language: str = "en", digits: int = 0, sign: bool = False) -> str:
    """20,909.5 in both languages: the Peruvian locale (CLDR es-PE) uses the same separators as
    English, and the web interface formats numbers the same way."""
    if value is None:
        return "—"
    return f"{value:{'+' if sign else ''},.{digits}f}"


class Doc:
    """Rendering context: language, labels and number formatting."""

    def __init__(self, report: dict[str, Any]):
        self.r = report
        self.lang = report["language"] if report["language"] in LABELS else "en"
        self.t = LABELS[self.lang]

    def n(self, value: Any, digits: int = 0, sign: bool = False) -> str:
        return format_number(value, self.lang, digits, sign)


# ------------------------------------------------------------------ chart primitives


def nice_max(value: float) -> float:
    """Smallest 'round' number (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 × 10^k) at or above ``value``."""
    if value <= 0:
        return 1.0
    exponent = 10 ** math.floor(math.log10(value))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * exponent:
            return step * exponent
    return 10 * exponent


def y_axis(doc: Doc, top: float, x0: float, x1: float, y0: float, y1: float, ticks: int = 4) -> str:
    out = []
    for i in range(ticks + 1):
        value = top * i / ticks
        y = y1 - (y1 - y0) * i / ticks
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x0 - 6}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10">{doc.n(value)}</text>')
    return "".join(out)


def x_labels(labels: list[str], xs: list[float], y: float, min_gap: float = 34) -> str:
    """Labels left to right, skipping any closer than ``min_gap`` px to the previous one; the last
    label is always kept and replaces the previous one if they would collide."""
    kept: list[tuple[str, float]] = []
    for label, x in zip(labels, xs, strict=True):
        if kept and x - kept[-1][1] < min_gap:
            if label == labels[-1]:
                kept[-1] = (label, x)
            continue
        kept.append((label, x))
    return "".join(f'<text x="{x:.1f}" y="{y}" text-anchor="middle" font-size="10">{esc(label)}</text>'
                   for label, x in kept)


def anomaly_colour(value: float | None) -> str:
    """ColorBrewer RdBu, 9 classes, symmetric around 0 (colour-blind safe)."""
    if value is None:
        return "url(#hatch)"
    steps = [(-60, "#2166ac"), (-40, "#4393c3"), (-20, "#92c5de"), (-7, "#d1e5f0"), (7, "#f7f7f7"),
             (20, "#fddbc7"), (40, "#f4a582"), (60, "#d6604d")]
    for limit, colour in steps:
        if value < limit:
            return colour
    return "#b2182b"


HATCH = ('<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         '<rect width="5" height="5" fill="#eef1f4"/><line x1="0" y1="0" x2="0" y2="5" stroke="#c4cbd3" stroke-width="2"/>'
         '</pattern></defs>')


# ------------------------------------------------------------------ sections


def cards(doc: Doc) -> str:
    t, s = doc.t, doc.r["sections"]
    month = s["current"]["month"]
    out = []

    def card(title: str, big: str, small: str = "") -> str:
        return f'<div class="card"><h3>{esc(title)}</h3><div class="big">{big}</div><div class="small">{small}</div></div>'

    def chip(value: float | None) -> str:
        if value is None:
            return ""
        kind = "up" if value >= 10 else "down" if value <= -10 else "flat"
        return f' <span class="chip {kind}">{doc.n(value, sign=True)} %</span>'

    if month["value"] is not None:
        rank = t["rank"].format(r=month["rank"], n=month["rank_of"]) if month["rank"] else ""
        out.append(card(t["card_month"], doc.n(month["value"]) + chip(month["anomaly_percent"]),
                        f'{esc(t["unit"])}<br>{esc(rank)}'))
    else:
        current = s["current"]["month_to_date"]
        if current and current["value"] is not None:
            out.append(card(t["card_month"], doc.n(current["value"]),
                            esc(t["days_so_far"].format(d=current["valid_days"])) + f'<br>{esc(t["unit"])}'))
        else:
            out.append(card(t["card_month"], esc(t["na"])))
    season = s["history"].get("season_jul_oct") or {}
    if season.get("rank"):
        out.append(card(t["card_season"], esc(t["rank"].format(r=season["rank"], n=season["rank_of"])),
                        chip(season.get("anomaly_percent"))))
    else:
        out.append(card(t["card_season"], esc(t["na"])))
    trend = s["history"].get("trend_harmonized") or {}
    raw = s["history"].get("trend_raw_pixels") or {}
    if trend.get("slope_pct_per_year") is not None:
        arrow = {"increase": "↑", "decrease": "↓"}.get(trend["direction"], "→")
        big = (f'{arrow} {doc.n(trend["slope_pct_per_year"], 1, True)} {t["per_year"]}' if trend["significant"]
               else f'→ {esc(t["no_trend"])}')
        small = esc(t["raw_note"].format(v=doc.n(raw.get("slope_pct_per_year"), 1, True))) if raw.get("significant") else ""
        out.append(card(t["card_trend"], big, small))
    else:
        out.append(card(t["card_trend"], esc(t["na"])))
    events = s["events"].get("selected_year") if s["events"]["status"] == "available" else None
    if events:
        emergencies = events.get("emergencies")
        if emergencies:
            small = t["per_emergency"].format(v=doc.n(events["significant_events"] / emergencies, 1))
        else:
            small = t["no_emergency"] if emergencies is None else ""
        out.append(card(t["card_events"], f'{doc.n(events["significant_events"])} / {doc.n(emergencies)}', esc(small)))
    else:
        out.append(card(t["card_events"], esc(t["na"])))
    forest = s["forest"] if s["forest"]["status"] == "available" else None
    row = None
    if forest and forest["by_year"]:
        row = forest.get("selected_year") or forest["by_year"][-1]
    if row:
        share = 100 * row["loss_ha_with_fire"] / row["loss_ha"] if row["loss_ha"] else None
        out.append(card(f'{t["card_forest"]} {row["year"]}', f'{doc.n(row["loss_ha"])} ha',
                        esc(t["with_fire"].format(v=doc.n(share))) if share is not None else ""))
    else:
        out.append(card(t["card_forest"], esc(t["na"])))
    climate = s["climate"]["selected_month"] if s["climate"]["status"] == "available" else None
    if climate:
        applicable = [c for c in climate if c["drought"] is not None]
        if not applicable:
            out.append(card(t["card_drought"], esc(t["drought_na"])))
        else:
            yes = sum(c["drought"] for c in applicable)
            big = (t["drought_yes"] + (f" ({yes}/{len(applicable)})" if len(applicable) > 1 else "")) if yes else t["drought_no"]
            pct = applicable[0].get("precip_percentile") if len(applicable) == 1 else None
            out.append(card(t["card_drought"], esc(big),
                            esc(t["precip_pct"].format(v=doc.n(pct))) if pct is not None else ""))
    else:
        out.append(card(t["card_drought"], esc(t["na"])))
    return '<div class="cards">' + "".join(out) + "</div>"


def profile_chart(doc: Doc) -> str:
    t, profile = doc.t, doc.r["sections"]["current"].get("profile") or []
    if not profile:
        return ""
    width, height, x0, x1, y0, y1 = 680, 230, 56, 668, 18, 196
    top = nice_max(max([p["p90"] or 0 for p in profile] + [p["value"] or 0 for p in profile]))
    step = (x1 - x0) / 12
    xs = [x0 + step * (i + 0.5) for i in range(12)]

    def scale(v: float) -> float:
        return y1 - (y1 - y0) * v / top

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(t["chart_profile"])}">']
    selected_month = doc.r["period"]["month"]
    out.append(f'<rect x="{xs[selected_month - 1] - step / 2:.1f}" y="{y0}" width="{step:.1f}" height="{y1 - y0}" fill="#fff7ed"/>')
    out.append(y_axis(doc, top, x0, x1, y0, y1))
    band = [(x, p) for x, p in zip(xs, profile, strict=True) if p["p10"] is not None]
    if band:
        upper = " ".join(f"{x:.1f},{scale(p['p90']):.1f}" for x, p in band)
        lower = " ".join(f"{x:.1f},{scale(p['p10']):.1f}" for x, p in reversed(band))
        out.append(f'<polygon points="{upper} {lower}" fill="{BAND}" opacity="0.9"/>')
        median = " ".join(f"{x:.1f},{scale(p['median']):.1f}" for x, p in band)
        out.append(f'<polyline fill="none" stroke="{MEDIAN}" stroke-width="1.5" stroke-dasharray="4 3" points="{median}"/>')
    points = [(x, p["value"]) for x, p in zip(xs, profile, strict=True) if p["value"] is not None]
    if points:
        out.append(f'<polyline fill="none" stroke="{FIRE}" stroke-width="2.5" points="'
                   + " ".join(f"{x:.1f},{scale(v):.1f}" for x, v in points) + '"/>')
        out += [f'<circle cx="{x:.1f}" cy="{scale(v):.1f}" r="3.2" fill="{FIRE}"/>' for x, v in points]
    sel = profile[selected_month - 1]
    if sel["value"] is not None:
        x, y = xs[selected_month - 1], scale(sel["value"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="none" stroke="{INK}" stroke-width="1.5"/>')
        out.append(f'<text x="{x:.1f}" y="{max(y - 11, y0 + 8):.1f}" text-anchor="middle" font-size="11" '
                   f'font-weight="700" fill="{INK}">{doc.n(sel["value"])}</text>')
    out.append(x_labels(t["months_short"], xs, y1 + 18, min_gap=10))
    out.append("</svg>")
    legend = (f'<div class="legend"><span><i style="background:{FIRE}"></i>{doc.r["period"]["year"]}</span>'
              f'<span><i style="background:{MEDIAN};height:2px;vertical-align:3px"></i>{esc(t["legend_median"])}</span>'
              f'<span><i style="background:{BAND}"></i>{esc(t["legend_band"])}</span></div>')
    return (f'<section><h2>{esc(t["chart_profile"])}</h2><p class="note">{esc(t["chart_profile_note"])} '
            f'{esc(t["unit"])}.</p>{"".join(out)}{legend}</section>')


def calendar_chart(doc: Doc) -> str:
    t, matrix = doc.t, doc.r["sections"]["current"].get("calendar") or []
    if not matrix:
        return ""
    selected_year, selected_month = doc.r["period"]["year"], doc.r["period"]["month"]
    first = min((m["year"] for m in matrix if m["value"] is not None), default=selected_year)
    years = list(range(first, selected_year + 1))
    lookup = {(m["year"], m["month"]): m for m in matrix}
    row, x0, cell_w = 13, 46, 51
    height = 22 + row * len(years) + 40
    out = [f'<svg viewBox="0 0 680 {height}" role="img" aria-label="{esc(t["chart_calendar"])}">', HATCH]
    for j, label in enumerate(t["months_short"]):
        out.append(f'<text x="{x0 + cell_w * (j + 0.5):.1f}" y="14" text-anchor="middle" font-size="10">{label}</text>')
    for i, year in enumerate(years):
        y = 20 + row * i
        weight = ' font-weight="700" fill="#17212b"' if year == selected_year else ""
        out.append(f'<text x="{x0 - 6}" y="{y + row - 3}" text-anchor="end" font-size="9.5"{weight}>{year}</text>')
        for j in range(12):
            m = lookup.get((year, j + 1))
            if m is None or m["value"] is None:
                fill = "url(#hatch)"
            elif m["anomaly_percent"] is None:
                fill = "#f1f5f9"
            else:
                fill = anomaly_colour(m["anomaly_percent"])
            out.append(f'<rect x="{x0 + cell_w * j + 1:.1f}" y="{y + 1}" width="{cell_w - 2}" height="{row - 2}" fill="{fill}" rx="1.5"/>')
    sel_index = years.index(selected_year) if selected_year in years else None
    if sel_index is not None:
        out.append(f'<rect x="{x0 + cell_w * (selected_month - 1):.1f}" y="{20 + row * sel_index}" width="{cell_w}" '
                   f'height="{row}" fill="none" stroke="{INK}" stroke-width="2"/>')
    legend_y = 20 + row * len(years) + 10
    scale = [(-70, "−60 %"), (-50, ""), (-30, ""), (-13, ""), (0, "0"), (13, ""), (30, ""), (50, ""), (70, "+60 %")]
    for k, (value, label) in enumerate(scale):
        out.append(f'<rect x="{x0 + 32 * k}" y="{legend_y}" width="32" height="9" fill="{anomaly_colour(value)}"/>')
        if label:
            out.append(f'<text x="{x0 + 32 * k + 16}" y="{legend_y + 21}" text-anchor="middle" font-size="9">{label}</text>')
    out.append(f'<rect x="{x0 + 32 * 9 + 24}" y="{legend_y}" width="32" height="9" fill="url(#hatch)"/>'
               f'<text x="{x0 + 32 * 10 + 30}" y="{legend_y + 8}" font-size="9">{esc(t["na"])}</text>')
    out.append("</svg>")
    return (f'<section><h2>{esc(t["chart_calendar"])}</h2><p class="note">{esc(t["chart_calendar_note"])}</p>'
            f'{"".join(out)}</section>')


def trend_chart(doc: Doc) -> str:
    t, history = doc.t, doc.r["sections"]["history"]
    rows = history.get("annual") or []
    base_h = [r["harmonized"] for r in rows if 2003 <= r["year"] <= 2011]
    base_r = [r["raw_pixels"] for r in rows if 2003 <= r["year"] <= 2011]
    if len(rows) < 6 or not base_h or not sum(base_h) or not sum(base_r):
        return ""
    mean_h, mean_r = sum(base_h) / len(base_h), sum(base_r) / len(base_r)
    series = [(r["year"], 100 * r["harmonized"] / mean_h, 100 * r["raw_pixels"] / mean_r) for r in rows]
    width, height, x0, x1, y0, y1 = 680, 240, 56, 664, 18, 206
    top = nice_max(max(max(h, w) for _, h, w in series))
    step = (x1 - x0) / max(1, len(series) - 1)
    xs = [x0 + step * i for i in range(len(series))]

    def scale(v: float) -> float:
        return y1 - (y1 - y0) * v / top

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(t["chart_trend"])}">',
           y_axis(doc, top, x0, x1, y0, y1)]
    base_y = scale(100)
    out.append(f'<line x1="{x0}" y1="{base_y:.1f}" x2="{x1}" y2="{base_y:.1f}" stroke="{MEDIAN}" stroke-width="1" stroke-dasharray="2 3"/>')
    years = [y for y, _, _ in series]
    if 2012 in years:
        x = xs[years.index(2012)]
        out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{INK}" stroke-width="1" stroke-dasharray="3 3"/>'
                   f'<text x="{x + 5:.1f}" y="{y0 + 10}" font-size="10" fill="{INK}">VIIRS 2012</text>')
    out.append(f'<polyline fill="none" stroke="{RAW}" stroke-width="2" stroke-dasharray="6 4" points="'
               + " ".join(f"{x:.1f},{scale(w):.1f}" for x, (_, _, w) in zip(xs, series, strict=True)) + '"/>')
    out.append(f'<polyline fill="none" stroke="{FIRE}" stroke-width="2.5" points="'
               + " ".join(f"{x:.1f},{scale(h):.1f}" for x, (_, h, _) in zip(xs, series, strict=True)) + '"/>')
    out.append(x_labels([str(y) for y in years], xs, y1 + 18, min_gap=42))
    out.append("</svg>")
    legend = (f'<div class="legend"><span><i style="background:{FIRE}"></i>{esc(t["legend_harmonized"])}</span>'
              f'<span><i style="background:{RAW}"></i>{esc(t["legend_raw"])}</span></div>')
    return (f'<section><h2>{esc(t["chart_trend"])}</h2><p class="note">{esc(t["chart_trend_note"])}</p>'
            f'{"".join(out)}{legend}</section>')


def events_chart(doc: Doc) -> str:
    t, events = doc.t, doc.r["sections"]["events"]
    if events["status"] != "available" or not events["by_year"]:
        return ""
    rows = events["by_year"]
    has_emergencies = any(r["emergencies"] is not None for r in rows)
    width, height, x0, x1, y0, y1 = 680, 220, 56, 668, 18, 186
    top = nice_max(max(max(r["significant_events"], r["emergencies"] or 0) for r in rows))
    group = (x1 - x0) / len(rows)
    bar = group * (0.36 if has_emergencies else 0.6)

    def height_of(v: float) -> float:
        return (y1 - y0) * v / top

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(t["chart_events"])}">',
           y_axis(doc, top, x0, x1, y0, y1)]
    xs = []
    for i, r in enumerate(rows):
        centre = x0 + group * (i + 0.5)
        xs.append(centre)
        left = centre - (bar if has_emergencies else bar / 2)
        h = height_of(r["significant_events"])
        out.append(f'<rect x="{left:.1f}" y="{y1 - h:.1f}" width="{bar:.1f}" height="{h:.1f}" fill="{FIRE}" rx="1"/>')
        if has_emergencies and r["emergencies"] is not None:
            h2 = height_of(r["emergencies"])
            out.append(f'<rect x="{centre:.1f}" y="{y1 - h2:.1f}" width="{bar:.1f}" height="{h2:.1f}" fill="{BLUE}" rx="1"/>')
    out.append(x_labels([str(r["year"]) for r in rows], xs, y1 + 18, min_gap=42))
    out.append("</svg>")
    legend = f'<div class="legend"><span><i style="background:{FIRE}"></i>{esc(t["legend_events"])}</span>'
    if has_emergencies:
        legend += f'<span><i style="background:{BLUE}"></i>{esc(t["legend_emergencies"])}</span>'
    legend += "</div>"
    return (f'<section><h2>{esc(t["chart_events"])}</h2><p class="note">{esc(t["chart_events_note"])}</p>'
            f'{"".join(out)}{legend}</section>{subdivision_chart(doc)}')


def subdivision_chart(doc: Doc) -> str:
    t, rows = doc.t, (doc.r["sections"]["events"].get("top_subdivisions") or [])[:8]
    if len(rows) < 2:
        return ""
    top = nice_max(max(max(r["events"], r["emergencies"]) for r in rows))
    row_h, x0, x1 = 28, 200, 630
    height = row_h * len(rows) + 8
    out = [f'<svg viewBox="0 0 680 {height}" role="img" aria-label="subdivisions">']
    for i, r in enumerate(rows):
        y = 4 + row_h * i
        out.append(f'<text x="{x0 - 8}" y="{y + 16}" text-anchor="end" font-size="11" fill="{INK}">{esc(r["name"])}</text>')
        w1 = (x1 - x0) * r["events"] / top
        w2 = (x1 - x0) * r["emergencies"] / top
        out.append(f'<rect x="{x0}" y="{y + 2}" width="{max(w1, 1):.1f}" height="10" fill="{FIRE}" rx="1"/>'
                   f'<text x="{x0 + w1 + 5:.1f}" y="{y + 11}" font-size="9.5">{doc.n(r["events"])}</text>')
        out.append(f'<rect x="{x0}" y="{y + 14}" width="{max(w2, 1):.1f}" height="10" fill="{BLUE}" rx="1"/>'
                   f'<text x="{x0 + w2 + 5:.1f}" y="{y + 23}" font-size="9.5">{doc.n(r["emergencies"])}</text>')
    out.append("</svg>")
    return f'<section><h2>{esc(t["chart_subdivisions"].format(y=doc.r["period"]["year"]))}</h2>{"".join(out)}</section>'


def forest_chart(doc: Doc) -> str:
    t, forest = doc.t, doc.r["sections"]["forest"]
    if forest["status"] != "available" or not forest["by_year"]:
        return ""
    rows = forest["by_year"]
    width, height, x0, x1, y0, y1 = 680, 220, 64, 668, 18, 186
    top = nice_max(max(r["loss_ha"] for r in rows))
    group = (x1 - x0) / len(rows)
    bar = group * 0.7

    def height_of(v: float) -> float:
        return (y1 - y0) * v / top

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(t["chart_forest"])}">',
           y_axis(doc, top, x0, x1, y0, y1)]
    xs = []
    for i, r in enumerate(rows):
        centre = x0 + group * (i + 0.5)
        xs.append(centre)
        fire, total = height_of(r["loss_ha_with_fire"]), height_of(r["loss_ha"])
        out.append(f'<rect x="{centre - bar / 2:.1f}" y="{y1 - total:.1f}" width="{bar:.1f}" height="{max(total - fire, 0):.1f}" fill="#fdba74"/>')
        out.append(f'<rect x="{centre - bar / 2:.1f}" y="{y1 - fire:.1f}" width="{bar:.1f}" height="{fire:.1f}" fill="{FIRE_DARK}"/>')
        if r["year"] == 2012 and i > 0:
            x = centre - group / 2
            out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{INK}" stroke-width="1" stroke-dasharray="3 3"/>'
                       f'<text x="{x + 5:.1f}" y="{y0 + 10}" font-size="10" fill="{INK}">{esc(t["method_break"])}</text>')
    out.append(x_labels([str(r["year"]) for r in rows], xs, y1 + 18, min_gap=42))
    out.append("</svg>")
    legend = (f'<div class="legend"><span><i style="background:{FIRE_DARK}"></i>{esc(t["legend_with_fire"])}</span>'
              f'<span><i style="background:#fdba74"></i>{esc(t["legend_other"])}</span></div>')
    caveats = "".join(f"<li>{esc(c)}</li>" for c in t["forest_caveats"])
    return (f'<section><h2>{esc(t["chart_forest"])} (ha)</h2><p class="note">{esc(t["forest_definition"])} '
            f'{esc(t["forest_validation"])}</p>{"".join(out)}{legend}'
            f'<div class="note"><ul style="margin:1mm 0 0 4mm;padding:0">{caveats}</ul></div></section>')


def climate_table(doc: Doc) -> str:
    t, climate = doc.t, doc.r["sections"]["climate"]
    if climate["status"] != "available":
        return ""
    rows = climate["selected_month"][:14]

    def dot(percentile: float | None) -> str:
        if percentile is None:
            return "—"
        colour = ("#b2182b" if percentile <= 20 else "#f4a582" if percentile <= 40
                  else "#cbd5e1" if percentile < 60 else "#4393c3")
        return (f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{colour};'
                f'margin-right:2mm"></span>{doc.n(percentile)}')

    body = "".join(
        f'<tr><td>{esc(r["department"])}</td><td>{dot(r.get("precip_percentile"))}</td><td>{doc.n(r["vpd_z"], 1, True)}</td>'
        f'<td>{esc(t["drought_na"] if r["drought"] is None else t["drought_yes"] if r["drought"] else t["drought_no"])}</td></tr>'
        for r in rows
    )
    month = t["months_long"][doc.r["period"]["month"] - 1]
    return (f'<section><h2>{esc(t["chart_climate"])} · {esc(month)} {doc.r["period"]["year"]}</h2>'
            f'<p class="note">{esc(t["climate_source"])} {esc(t["climate_note"])}</p>'
            f'<table><tr><th>{esc(t["col_department"])}</th><th>{esc(t["col_precip"])}</th><th>{esc(t["col_vpd"])}</th>'
            f'<th>{esc(t["col_drought"])}</th></tr>{body}</table></section>')


def imagery(doc: Doc) -> str:
    t, image = doc.t, doc.r["sections"].get("imagery") or {}
    if image.get("status") != "available":
        return ""
    west, south, east, north = image["bbox"]
    width = 640
    height = max(200, min(900, round(width * (north - south) / max(east - west, 1e-6))))
    rings = []
    for ring in image["outline"]:
        points = " ".join(f"{(x - west) / (east - west) * width:.1f},{(north - y) / (north - south) * height:.1f}"
                          for x, y in ring)
        rings.append(f'<polygon points="{points}" fill="none" stroke="#fde047" stroke-width="2.5"/>')
    overlay = f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">{"".join(rings)}</svg>'
    figures = []
    for which in ("before", "after"):
        shot = image[which]
        src = f'/api/reports/territorial/{esc(doc.r["id"])}/imagery/{which}'
        figures.append(f'<figure><div class="frame"><img src="{src}" alt="{esc(shot["date"])}">{overlay}</div>'
                       f'<figcaption>{esc(t[which].format(d=shot["date"]))}</figcaption></figure>')
    return (f'<section><h2>{esc(t["chart_imagery"])}</h2><div class="images">{"".join(figures)}</div>'
            f'<p class="note">{esc(t["imagery_note"])}</p></section>')


def quality(doc: Doc) -> str:
    t, q = doc.t, doc.r["sections"]["quality"]
    items = [
        t["q_support"].format(v=doc.n(q["valid_region_days"]), e=doc.n(q["expected_region_days"]),
                              f=doc.n(q["noaa20_filled_days"]), u=f'{doc.n(100 * q["unvalidated_share"], 1)} %'),
        t["typical_error"],
        t["q_unit"],
    ]
    for section in ("events", "forest", "climate"):
        reason = doc.r["sections"][section].get("reason")
        if doc.r["sections"][section]["status"] != "available" and reason:
            items.append(f"{section}: {reason}.")
    return (f'<section><h2>{esc(t["quality"])}</h2><div class="box"><ul>'
            + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul></div></section>")


def render(report: dict[str, Any]) -> str:
    doc = Doc(report)
    t = doc.t
    territory = report["territory"]
    month_name = t["months_long"][report["period"]["month"] - 1]
    period = f'{month_name[0].upper()}{month_name[1:]} {report["period"]["year"]}'
    head = report.get("headline") or {}
    headline_text = head.get("text") or (report["summary"][0] if report["summary"] else "")
    badge = f'<div class="badge">{esc(t["experimental"])}</div>' if report["validation_status"] != "validated" else ""
    parts = [
        f"<!doctype html><html lang='{doc.lang}'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>NINA · {esc(territory['name'])} · {esc(period)}</title><style>{CSS}</style></head><body>",
        f'<div class="toolbar"><button onclick="window.print()">{esc(t["print"])}</button></div>',
        f'<header><div><p class="kicker">{esc(t["kicker"])}</p><h1>{esc(territory["name"])}</h1>'
        f'<p class="subtitle">{esc(period)} · {esc(t["type"].get(territory["type"], territory["type"]))}</p></div>{badge}</header>',
        f'<div class="headline {esc(head.get("kind", ""))}">{esc(headline_text)}</div>',
        cards(doc),
        profile_chart(doc),
        calendar_chart(doc),
        '<div class="page-break"></div>',
        trend_chart(doc),
        events_chart(doc),
        forest_chart(doc),
        climate_table(doc),
        imagery(doc),
        quality(doc),
        f'<section><h2>{esc(t["sources"])}</h2><p class="note">NINA {esc(report["method_version"])} · dataset '
        f'{esc(report["dataset_id"])} · report {esc(report["id"])} · {esc(report["generated_at"])}<br>'
        + " · ".join(esc(r) for r in report["references"]) + "</p></section>",
        f'<footer>{esc(report["legal"])}</footer></body></html>',
    ]
    return "".join(parts)
