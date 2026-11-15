"""Printable HTML for the territorial report (A4, inline SVG, no external assets).

Only renders facts already computed by ``nina.reports``; it never computes or invents numbers.
"""

from __future__ import annotations

import html
from typing import Any

LABELS = {
    "en": {
        "title": "Territorial fire evidence report",
        "experimental": "Experimental harmonized product: not an official document and not for tactical decisions.",
        "summary": "Executive summary",
        "current": "1. Current situation",
        "history": "2. Historical context and trend",
        "events": "3. Detected fire events and recorded emergencies",
        "forest": "4. Tree-cover loss associated with fire activity",
        "climate": "5. Climatic conditions",
        "quality": "6. Quality and limitations",
        "provenance": "7. Reproducibility",
        "not_available": "Not available for this territory",
        "month": "Month", "value": "VIIRS-eq. active cell-days", "anomaly": "Anomaly", "rank": "Rank",
        "year": "Year", "harmonized": "Harmonized", "raw": "Raw pixels (not comparable across sensors)",
        "events_col": "Significant events", "emergencies_col": "INDECI emergencies", "subdivision": "Subdivision",
        "loss": "Loss (ha)", "loss_fire": "Loss in cells with fire (ha)", "department": "Department",
        "precip": "Precipitation z", "vpd": "VPD z", "drought": "Drought",
        "unit_note": "Unit: active H3 cells (~5 km²) per day, VIIRS S-NPP-equivalent scale.",
        "yes": "yes", "no": "no", "na_short": "n/a (dry month)", "percentile": "Rain percentile",
    },
    "es": {
        "title": "Informe técnico territorial de actividad de fuego",
        "experimental": "Producto armonizado experimental: no es un documento oficial ni sirve para decisiones tácticas.",
        "summary": "Resumen ejecutivo",
        "current": "1. Situación actual",
        "history": "2. Contexto histórico y tendencia",
        "events": "3. Eventos de incendio detectados y emergencias registradas",
        "forest": "4. Pérdida de cobertura arbórea asociada a la actividad de fuego",
        "climate": "5. Condiciones climáticas",
        "quality": "6. Calidad y limitaciones",
        "provenance": "7. Reproducibilidad",
        "not_available": "No disponible para este territorio",
        "month": "Mes", "value": "Celdas-día activas eq. VIIRS", "anomaly": "Anomalía", "rank": "Puesto",
        "year": "Año", "harmonized": "Armonizado", "raw": "Píxeles crudos (no comparables entre sensores)",
        "events_col": "Eventos significativos", "emergencies_col": "Emergencias INDECI", "subdivision": "Subdivisión",
        "loss": "Pérdida (ha)", "loss_fire": "Pérdida en celdas con fuego (ha)", "department": "Departamento",
        "precip": "Precipitación z", "vpd": "DPV z", "drought": "Sequía",
        "unit_note": "Unidad: celdas H3 activas (~5 km²) por día, en escala equivalente a VIIRS S-NPP.",
        "yes": "sí", "no": "no", "na_short": "no aplica (mes seco)", "percentile": "Percentil de lluvia",
    },
}

CSS = """
@page { size: A4; margin: 14mm; }
body { font: 10.5pt/1.45 "Segoe UI", system-ui, sans-serif; color: #1c2430; background: #fff; margin: 0 auto; max-width: 182mm; }
h1 { font-size: 17pt; margin: 0 0 2mm; }
h2 { font-size: 12pt; margin: 6mm 0 2mm; border-bottom: 1px solid #c9d1db; padding-bottom: 1mm; break-after: avoid; }
.meta { color: #4a5666; font-size: 9pt; }
.flag { background: #fff4e5; border-left: 3px solid #d9822b; padding: 2mm 3mm; font-size: 9pt; margin: 3mm 0; }
ul.summary li { margin: 1mm 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 2mm 0; }
th, td { border-bottom: 1px solid #e3e7ec; padding: 1.2mm 1.5mm; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { color: #4a5666; font-weight: 600; }
.na { color: #7a8594; font-style: italic; }
svg text { font: 8pt "Segoe UI", system-ui, sans-serif; fill: #4a5666; }
footer { margin-top: 6mm; font-size: 8pt; color: #4a5666; border-top: 1px solid #c9d1db; padding-top: 2mm; }
@media print { .noprint { display: none; } }
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def format_number(value: Any, language: str = "en", digits: int = 0, sign: bool = False) -> str:
    """English: 20,909.5. Spanish (Peruvian SLUMP norm): 20 909,5 with a thin space for thousands."""
    if value is None:
        return "—"
    text = f"{value:{'+' if sign else ''},.{digits}f}"
    if language == "es":
        text = text.replace(",", " ").replace(".", ",")
    return text


LANGUAGE = {"value": "en"}


def num(value: Any, digits: int = 0) -> str:
    return format_number(value, LANGUAGE["value"], digits)


def pct(value: Any) -> str:
    return "—" if value is None else format_number(value, LANGUAGE["value"], 0, sign=True) + " %"


def anomaly_colour(value: float | None) -> str:
    """Diverging blue–white–red ramp (colour-blind safe endpoints); grey for missing."""
    if value is None:
        return "#d5d9df"
    ratio = max(-1.0, min(1.0, value / 100))
    if ratio >= 0:
        r, g, b = 255, int(255 - 160 * ratio), int(255 - 200 * ratio)
    else:
        r, g, b = int(255 + 200 * ratio), int(255 + 110 * ratio), 255
    return f"#{r:02x}{g:02x}{b:02x}"


def strip_svg(months: list[dict]) -> str:
    width, cell = 520, 520 / max(1, len(months))
    parts = [f'<svg width="{width}" height="46" role="img" aria-label="12-month anomaly strip">']
    for i, m in enumerate(months):
        colour = anomaly_colour(m["anomaly_percent"]) if m["value"] is not None else "#d5d9df"
        parts.append(f'<rect x="{i * cell:.1f}" y="0" width="{cell - 2:.1f}" height="28" fill="{colour}" rx="2"/>')
        parts.append(f'<text x="{i * cell + cell / 2:.1f}" y="40" text-anchor="middle">{m["year"] % 100:02d}/{m["month"]:02d}</text>')
    parts.append("</svg>")
    return "".join(parts)


def series_svg(rows: list[dict]) -> str:
    """Harmonized vs raw annual series, each scaled to its own maximum (shape comparison)."""
    if not rows:
        return ""
    width, height, pad = 520, 150, 24
    harm_max = max(r["harmonized"] for r in rows) or 1
    raw_max = max(r["raw_pixels"] for r in rows) or 1
    step = (width - 2 * pad) / max(1, len(rows) - 1)

    def path(key: str, top: float) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{pad + i * step:.1f},{height - pad - (r[key] / top) * (height - 2 * pad):.1f}"
            for i, r in enumerate(rows)
        )

    labels = "".join(
        f'<text x="{pad + i * step:.1f}" y="{height - 6}" text-anchor="middle">{r["year"]}</text>'
        for i, r in enumerate(rows) if i % 4 == 0 or i == len(rows) - 1
    )
    return (
        f'<svg width="{width}" height="{height}" role="img" aria-label="annual series">'
        f'<path d="{path("raw_pixels", raw_max)}" fill="none" stroke="#9aa5b1" stroke-width="1.5" stroke-dasharray="4 3"/>'
        f'<path d="{path("harmonized", harm_max)}" fill="none" stroke="#c0392b" stroke-width="2"/>'
        f"{labels}</svg>"
    )


def render(report: dict[str, Any]) -> str:
    t = LABELS.get(report["language"], LABELS["en"])
    LANGUAGE["value"] = report["language"]
    s = report["sections"]
    territory = report["territory"]
    period = f"{report['period']['year']}-{report['period']['month']:02d}"
    out = [
        "<!doctype html><html lang='" + esc(report["language"]) + "'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>NINA · {esc(territory['name'])} · {period}</title><style>{CSS}</style></head><body>",
        f"<h1>{t['title']}</h1>",
        f"<div class='meta'><strong>{esc(territory['name'])}</strong> · {period} · "
        f"{esc(territory['type'])} · {num(territory['cells'])} H3 cells · NINA {esc(report['method_version'])} · "
        f"dataset {esc(report['dataset_id'])} · {esc(report['generated_at'])}</div>",
    ]
    if report["validation_status"] != "validated":
        out.append(f"<div class='flag'>{t['experimental']}</div>")
    out.append(f"<h2>{t['summary']}</h2><ul class='summary'>")
    out += [f"<li>{esc(line)}</li>" for line in report["summary"]]
    out.append(f"</ul><p class='meta'>{t['unit_note']}</p>")

    current = s["current"]
    out.append(f"<h2>{t['current']}</h2>{strip_svg(current['last_12_months'])}")
    out.append(f"<table><tr><th>{t['month']}</th><th>{t['value']}</th><th>{t['anomaly']}</th><th>{t['rank']}</th></tr>")
    for m in current["last_12_months"][-6:]:
        rank = f"{m['rank']}/{m['rank_of']}" if m["rank"] else "—"
        out.append(f"<tr><td>{m['year']}-{m['month']:02d}</td><td>{num(m['value'])}</td>"
                   f"<td>{pct(m['anomaly_percent'])}</td><td>{rank}</td></tr>")
    out.append("</table>")

    history = s["history"]
    out.append(f"<h2>{t['history']}</h2>")
    if history["status"] == "available":
        out.append(series_svg(history["annual"]))
        out.append(f"<p class='meta'><span style='color:#c0392b'>━</span> {t['harmonized']} &nbsp; "
                   f"<span style='color:#9aa5b1'>┅</span> {t['raw']}</p>")
    else:
        out.append(f"<p class='na'>{t['not_available']}</p>")

    events = s["events"]
    out.append(f"<h2>{t['events']}</h2>")
    if events["status"] == "available":
        out.append(f"<p class='meta'>{esc(events['rule'])}. {esc(events.get('emergencies_source') or '')}</p>")
        out.append(f"<table><tr><th>{t['year']}</th><th>{t['events_col']}</th><th>{t['emergencies_col']}</th></tr>")
        for row in events["by_year"][-8:]:
            out.append(f"<tr><td>{row['year']}</td><td>{num(row['significant_events'])}</td>"
                       f"<td>{num(row['emergencies'])}</td></tr>")
        out.append("</table>")
        if events["top_subdivisions"]:
            out.append(f"<table><tr><th>{t['subdivision']} ({report['period']['year']})</th>"
                       f"<th>{t['events_col']}</th><th>{t['emergencies_col']}</th></tr>")
            for row in events["top_subdivisions"]:
                out.append(f"<tr><td>{esc(row['name'])}</td><td>{num(row['events'])}</td><td>{num(row['emergencies'])}</td></tr>")
            out.append("</table>")
    else:
        out.append(f"<p class='na'>{t['not_available']}</p>")

    forest = s["forest"]
    out.append(f"<h2>{t['forest']}</h2>")
    if forest["status"] == "available":
        out.append(f"<p class='meta'>{esc(forest['definition'])}. {esc(forest.get('validation') or '')}</p>")
        out.append("<ul class='meta'>" + "".join(f"<li>{esc(c)}</li>" for c in forest.get("caveats", [])) + "</ul>")
        out.append(f"<table><tr><th>{t['year']}</th><th>{t['loss']}</th><th>{t['loss_fire']}</th></tr>")
        for row in forest["by_year"][-8:]:
            out.append(f"<tr><td>{row['year']}</td><td>{num(row['loss_ha'])}</td><td>{num(row['loss_ha_with_fire'])}</td></tr>")
        out.append("</table>")
    else:
        out.append(f"<p class='na'>{t['not_available']}</p>")

    climate = s["climate"]
    out.append(f"<h2>{t['climate']}</h2>")
    if climate["status"] == "available":
        out.append(f"<p class='meta'>{esc(climate['source'])}. {esc(climate['note'])}</p>")
        out.append(f"<table><tr><th>{t['department']}</th><th>{t['precip']}</th><th>{t['percentile']}</th>"
                   f"<th>{t['vpd']}</th><th>{t['drought']}</th></tr>")
        for row in climate["selected_month"]:
            state = t["na_short"] if row["drought"] is None else (t["yes"] if row["drought"] else t["no"])
            out.append(f"<tr><td>{esc(row['department'])}</td><td>{num(row['precip_z'], 2)}</td>"
                       f"<td>{num(row.get('precip_percentile'))}</td><td>{num(row['vpd_z'], 2)}</td><td>{state}</td></tr>")
        out.append("</table>")
    else:
        out.append(f"<p class='na'>{t['not_available']}</p>")

    quality = s["quality"]
    out.append(f"<h2>{t['quality']}</h2><ul class='meta'>")
    out.append(f"<li>Valid region-days: {quality['valid_region_days']} / {quality['expected_region_days']}; "
               f"NOAA-20-filled days: {quality['noaa20_filled_days']}; unvalidated share: {quality['unvalidated_share']:.2%}.</li>")
    out.append(f"<li>{esc(quality['typical_yearly_error'])}.</li>")
    out.append(f"<li>Gates: {esc(quality['gates'])}.</li></ul>")

    out.append(f"<h2>{t['provenance']}</h2><p class='meta'>Report {esc(report['id'])} · request "
               f"{esc(report['request'])} · references: {' · '.join(esc(r) for r in report['references'])}</p>")
    out.append(f"<footer>{esc(report['legal'])}</footer>")
    out.append("<p class='noprint meta'><button onclick='window.print()'>Print / PDF</button></p></body></html>")
    return "".join(out)
