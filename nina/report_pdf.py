"""Territorial report as a real PDF (ReportLab), downloaded in one click instead of printed from the browser.

The charts are the same SVG drawn for the HTML document (``report_document``), converted element by element into
ReportLab vector graphics, so the PDF and the web page show identical figures. Text uses the standard Helvetica
font: characters outside its encoding are replaced by close equivalents (``−`` → ``-``, ``≥`` → ``>=``).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Group, Image as DrawingImage, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from . import report_document as rd

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
INK = colors.HexColor("#17212b")
MUTED = colors.HexColor("#5b6670")
LINE = colors.HexColor("#d9dee3")
ACCENT = colors.HexColor("#c2410c")
SOFT = colors.HexColor("#f6f3ee")
HATCH_FILL = colors.HexColor("#e5e9ee")

REPLACEMENTS = {"−": "-", "‑": "-", "≥": ">=", "≤": "<=", "→": "->", "↑": "+", "↓": "-", "✓": "v", "≈": "~",
                "²": "2", " ": " ", " ": " "}


def clean(text: Any) -> str:
    """Text safe for Helvetica (WinAnsi): known symbols replaced, anything else outside cp1252 dropped."""
    value = "" if text is None else str(text)
    for old, new in REPLACEMENTS.items():
        value = value.replace(old, new)
    return value.encode("cp1252", "replace").decode("cp1252").replace("?", "?")


def para(text: Any) -> str:
    return escape(clean(text))


STYLES = {
    "kicker": ParagraphStyle("kicker", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=10),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, textColor=INK, leading=26),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10.5, textColor=MUTED, leading=14),
    "headline": ParagraphStyle("headline", fontName="Helvetica-Bold", fontSize=12, textColor=INK, leading=16),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, textColor=INK, leading=16, spaceBefore=8,
                         spaceAfter=3),
    "part": ParagraphStyle("part", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT, leading=12, spaceAfter=2),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, textColor=INK, leading=12.5),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=7.8, textColor=MUTED, leading=10.2),
    "check": ParagraphStyle("check", fontName="Helvetica", fontSize=8.2, textColor=INK, leading=11, backColor=SOFT,
                            borderPadding=(4, 5, 4, 5), spaceBefore=4, spaceAfter=4),
    "badge": ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=7.5, textColor=ACCENT, leading=10),
    "card_title": ParagraphStyle("card_title", fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=9.5),
    "card_big": ParagraphStyle("card_big", fontName="Helvetica-Bold", fontSize=14, textColor=INK, leading=17),
    "card_small": ParagraphStyle("card_small", fontName="Helvetica", fontSize=7.3, textColor=MUTED, leading=9.3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, textColor=INK, leading=10, alignment=TA_LEFT),
}


# ------------------------------------------------------------------ SVG (our own subset) -> ReportLab drawing

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def colour(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    value = value.strip()
    if value in {"none", "transparent"}:
        return None
    if value.startswith("url("):
        return HATCH_FILL
    if value.startswith("#"):
        if len(value) == 4:
            value = "#" + "".join(c * 2 for c in value[1:])
        return colors.HexColor(value)
    return getattr(colors, value, default)


def svg_drawing(svg: str, width: float) -> Drawing | None:
    """Convert the SVG produced by ``report_document`` (rect, line, polyline, polygon, circle, text) to a
    vector drawing ``width`` points wide. Returns None when there is no SVG."""
    match = re.search(r"<svg\b.*?</svg>", svg, re.S)
    if not match:
        return None
    root = ET.fromstring(match.group(0))
    _, _, view_w, view_h = (float(v) for v in root.get("viewBox", "0 0 680 230").split())
    group = Group()

    def y(value: str | float) -> float:
        return view_h - float(value)

    hidden = {id(child) for defs in root.iter() if defs.tag.split("}")[-1] == "defs" for child in defs.iter()}
    for element in root.iter():
        if id(element) in hidden:
            continue
        tag = element.tag.split("}")[-1]
        a = element.attrib
        fill = colour(a.get("fill"), INK if tag == "text" else None)
        stroke = colour(a.get("stroke"))
        stroke_width = float(a.get("stroke-width", 1))
        dash = [float(v) for v in NUMBER.findall(a.get("stroke-dasharray", ""))] or None
        opacity = float(a.get("opacity", 1))
        if tag == "rect":
            w, h = float(a.get("width", 0)), float(a.get("height", 0))
            shape = Rect(float(a.get("x", 0)), y(float(a.get("y", 0)) + h), w, h, fillColor=fill,
                         strokeColor=stroke, strokeWidth=stroke_width if stroke else 0)
        elif tag == "line":
            shape = Line(float(a["x1"]), y(a["y1"]), float(a["x2"]), y(a["y2"]), strokeColor=stroke or INK,
                         strokeWidth=stroke_width, strokeDashArray=dash)
        elif tag in {"polyline", "polygon"}:
            values = [float(v) for v in NUMBER.findall(a.get("points", ""))]
            points: list[float] = []
            for i in range(0, len(values) - 1, 2):
                points += [values[i], y(values[i + 1])]
            if len(points) < 4:
                continue
            if tag == "polygon":
                shape = Polygon(points, fillColor=fill, strokeColor=stroke, strokeWidth=stroke_width if stroke else 0)
            else:
                shape = PolyLine(points, strokeColor=stroke or INK, strokeWidth=stroke_width, strokeDashArray=dash)
        elif tag == "circle":
            shape = Circle(float(a["cx"]), y(a["cy"]), float(a["r"]), fillColor=fill,
                           strokeColor=stroke, strokeWidth=stroke_width if stroke else 0)
        elif tag == "text":
            anchor = {"middle": "middle", "end": "end"}.get(a.get("text-anchor", ""), "start")
            font = "Helvetica-Bold" if a.get("font-weight") in {"700", "bold"} else "Helvetica"
            shape = String(float(a.get("x", 0)), y(a.get("y", 0)), clean("".join(element.itertext())),
                           fontName=font, fontSize=float(a.get("font-size", 10)), fillColor=fill or MUTED,
                           textAnchor=anchor)
        else:
            continue
        if opacity < 1:
            for attribute in ("fillOpacity", "strokeOpacity"):
                if hasattr(shape, attribute):
                    setattr(shape, attribute, opacity)
        group.add(shape)
    scale = width / view_w
    group.scale(scale, scale)
    drawing = Drawing(width, view_h * scale)
    drawing.add(group)
    return drawing


def legend(items: list[tuple[str, str]]) -> Table:
    cells, widths = [], []
    for colour_value, label in items:
        swatch = Drawing(8, 8)
        swatch.add(Rect(0, 1, 8, 6, fillColor=colors.HexColor(colour_value), strokeColor=None))
        text = clean(label)
        cells += [swatch, Paragraph(para(text), STYLES["note"])]
        widths += [10, stringWidth(text, "Helvetica", 7.8) + 14]
    table = Table([cells], colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return table


# ------------------------------------------------------------------ document blocks


def header_block(doc: rd.Doc) -> list[Any]:
    t, r = doc.t, doc.r
    month = t["months_long"][r["period"]["month"] - 1]
    period = f"{month[0].upper()}{month[1:]} {r['period']['year']}"
    territory = r["territory"]
    flow: list[Any] = [Paragraph(para(t["kicker"]), STYLES["kicker"]), Spacer(1, 2),
                       Paragraph(para(territory["name"]), STYLES["title"]),
                       Paragraph(para(f"{period} · {t['type'].get(territory['type'], territory['type'])}"),
                                 STYLES["subtitle"])]
    if r["validation_status"] != "validated":
        flow += [Spacer(1, 3), Paragraph(para(t["experimental"]), STYLES["badge"])]
    head = r.get("headline") or {}
    text = head.get("text") or (r["summary"][0] if r["summary"] else "")
    if text:
        box = Table([[Paragraph(para(text), STYLES["headline"])]], colWidths=[CONTENT_W])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        flow += [Spacer(1, 8), box]
    return flow


def cards_block(doc: rd.Doc) -> Table:
    cells = []
    vs = "vs median" if doc.lang == "en" else "vs mediana"
    for card in rd.card_items(doc):
        cell: list[Any] = [Paragraph(para(card["title"]), STYLES["card_title"]), Spacer(1, 2),
                           Paragraph(para(card["big"]), STYLES["card_big"])]
        if card.get("chip"):
            value = float(card["chip"].replace(",", "").replace("%", "").strip())
            tone = "#b2182b" if value >= 10 else "#2166ac" if value <= -10 else "#5b6670"
            cell.append(Paragraph(f'<font color="{tone}"><b>{para(card["chip"])}</b></font> {vs}', STYLES["card_small"]))
        cell += [Spacer(1, 1), Paragraph(para(card["small"]).replace("\n", "<br/>"), STYLES["card_small"])]
        cells.append(cell)
    width = CONTENT_W / max(1, len(cells))
    table = Table([cells], colWidths=[width] * len(cells))
    table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    return table


def section(title: str, note: str | None, svg: str, legend_items: list[tuple[str, str]] | None = None,
            extra: list[Any] | None = None) -> list[Any]:
    drawing = svg_drawing(svg, CONTENT_W) if svg else None
    if drawing is None and not extra:
        return []
    block: list[Any] = [Paragraph(para(title), STYLES["h2"])]
    if note:
        block.append(Paragraph(para(note), STYLES["note"]))
        block.append(Spacer(1, 3))
    if drawing is not None:
        block.append(drawing)
    if legend_items:
        block.append(legend(legend_items))
    return [KeepTogether(block), *(extra or [])]


def checks(html: str) -> list[Any]:
    """Validation notes rendered by report_document as <p class="check">."""
    return [Paragraph(para(rd.html.unescape(m)), STYLES["check"]) for m in re.findall(r'<p class="check">(.*?)</p>', html, re.S)]


def table_block(header: list[str], rows: list[list[Any]], widths: list[float]) -> Table:
    data = [[Paragraph(f"<b>{para(h)}</b>", STYLES["cell"]) for h in header]]
    data += [[Paragraph(para(c), STYLES["cell"]) for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return table


def imagery_block(doc: rd.Doc, image_paths: dict[str, Path]) -> list[Any]:
    t, image = doc.t, doc.r["sections"].get("imagery") or {}
    if image.get("status") != "available" or not image_paths:
        return []
    west, south, east, north = image["bbox"]
    cell_w = (CONTENT_W - 6 * mm) / 2
    aspect = (north - south) / max(east - west, 1e-6)
    cell_h = min(cell_w * aspect, 95 * mm)
    cell_w_used = cell_h / aspect if aspect else cell_w
    row = []
    for which in ("before", "after"):
        path = image_paths.get(which)
        if not path:
            continue
        drawing = Drawing(cell_w_used, cell_h)
        drawing.add(DrawingImage(0, 0, cell_w_used, cell_h, str(path)))
        for ring in image["outline"]:
            points: list[float] = []
            for x, yy in ring:
                points += [(x - west) / (east - west) * cell_w_used, (yy - south) / (north - south) * cell_h]
            if len(points) >= 6:
                drawing.add(Polygon(points, fillColor=None, strokeColor=colors.HexColor("#fde047"), strokeWidth=1.4))
        row.append([drawing, Paragraph(para(t[which].format(d=image[which]["date"])), STYLES["note"])])
    if not row:
        return []
    grid = Table([row], colWidths=[cell_w + 3 * mm] * len(row), hAlign="LEFT")
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [KeepTogether([Paragraph(para(t["chart_imagery"]), STYLES["h2"]), grid,
                          Paragraph(para(t["imagery_note"]), STYLES["note"])])]


def build_pdf(report: dict[str, Any], image_paths: dict[str, Path] | None = None) -> bytes:
    """The report as A4 PDF bytes: summary page, evidence, detail and annex, with page numbers and the
    FIRMS legal notice."""
    doc = rd.Doc(report)
    t, s = doc.t, report["sections"]
    flow: list[Any] = [*header_block(doc), Spacer(1, 9), cards_block(doc)]
    flow += section(t["chart_profile"], f'{t["chart_profile_note"]} {t["unit"]}.', rd.profile_chart(doc),
                    [(rd.FIRE, str(report["period"]["year"])), (rd.MEDIAN, t["legend_median"]),
                     (rd.BAND, t["legend_band"])])
    points = rd.key_points(doc)
    items = re.findall(r"<li>(.*?)</li>", points, re.S)
    if items:
        flow.append(Paragraph(para(t["key_points"]), STYLES["h2"]))
        flow += [Paragraph("&bull; " + para(rd.html.unescape(i)), STYLES["body"]) for i in items]
    flow += [Spacer(1, 6), Paragraph(para(t["scope"]), STYLES["note"])]

    trend, events = rd.trend_chart(doc), rd.events_chart(doc)
    if trend or events or rd.burned_chart(doc):
        flow += [PageBreak(), Paragraph(para(t["part_evidence"]).upper(), STYLES["part"])]
        flow += section(t["chart_trend"], t["chart_trend_note"], trend,
                        [(rd.FIRE, t["legend_harmonized"]), (rd.RAW, t["legend_raw"])])
        if events:
            label = s["events"].get("emergencies_label") or t["legend_emergencies"]
            flow += section(t["chart_events"], t["chart_events_note"], events,
                            [(rd.FIRE, t["legend_events"]), (rd.BLUE, label)], checks(events))

    burned = rd.burned_chart(doc)
    if burned:
        unit = (s.get("burned_area") or {}).get("unit", "")
        flow += section(f'{t["chart_burned"]} (ha)', rd.fill(t["chart_burned_note"], unit=unit), burned, None,
                        checks(burned))

    forest = rd.forest_chart(doc)
    pictures = imagery_block(doc, image_paths or {})
    if forest or pictures:
        flow.append(PageBreak())
        if forest:
            labels = rd.forest_labels(doc)
            flow += section(f'{t["chart_forest"]} (ha)', f'{labels["definition"]} {labels["validation"]}'.strip(), forest,
                            [(rd.FIRE_DARK, labels["fire"]), ("#fdba74", labels["other"])],
                            checks(forest) + [Paragraph("&bull; " + para(c), STYLES["note"]) for c in labels["caveats"]])
        flow += pictures

    flow += [PageBreak(), Paragraph(para(t["part_annex"]).upper(), STYLES["part"])]
    flow += section(t["chart_calendar"], t["chart_calendar_note"], rd.calendar_chart(doc))
    subdivisions = (s["events"].get("top_subdivisions") or [])[:8] if s["events"]["status"] == "available" else []
    if len(subdivisions) >= 2:
        label = s["events"].get("emergencies_label") or t["col_emergencies"]
        flow += [Paragraph(para(t["chart_subdivisions"].format(y=report["period"]["year"])), STYLES["h2"]),
                 table_block([t["col_subdivision"], t["col_events"], label],
                             [[r["name"], doc.n(r["events"]), doc.n(r["emergencies"])] for r in subdivisions],
                             [CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25])]
    if s["climate"]["status"] == "available":
        month = t["months_long"][report["period"]["month"] - 1]
        rows = [[r["department"], doc.n(r.get("precip_percentile")), doc.n(r["vpd_z"], 1, True),
                 t["drought_na"] if r["drought"] is None else t["drought_yes"] if r["drought"] else t["drought_no"]]
                for r in s["climate"]["selected_month"][:14]]
        flow += [Paragraph(para(f'{t["chart_climate"]} · {month} {report["period"]["year"]}'), STYLES["h2"]),
                 Paragraph(para(f'{t["climate_source"]} {t["climate_note"]}'), STYLES["note"]), Spacer(1, 3),
                 table_block([t["col_department"], t["col_precip"], t["col_vpd"], t["col_drought"]], rows,
                             [CONTENT_W * 0.34, CONTENT_W * 0.22, CONTENT_W * 0.22, CONTENT_W * 0.22]),
                 *checks(rd.climate_table(doc))]
    quality = re.findall(r"<li>(.*?)</li>", rd.quality(doc), re.S)
    flow += [Paragraph(para(t["quality"]), STYLES["h2"])]
    flow += [Paragraph("&bull; " + para(rd.html.unescape(q)), STYLES["body"]) for q in quality]
    flow += [Paragraph(para(t["sources"]), STYLES["h2"]),
             Paragraph(para(f'NINA {report["method_version"]} · dataset {report["dataset_id"]} · report '
                            f'{report["id"]} · {report["generated_at"]}'), STYLES["note"]),
             *[Paragraph(para(reference), STYLES["note"]) for reference in report["references"]],
             Spacer(1, 6), Paragraph(para(report["legal"]), STYLES["note"])]

    buffer = io.BytesIO()
    footer_text = clean(f'NINA · {report["territory"]["name"]} · dataset {report["dataset_id"]} · '
                        + ("FIRMS data are not suitable for tactical or local-scale decisions"
                           if doc.lang == "en" else "Los datos FIRMS no son aptos para decisiones tácticas o locales"))

    def decorate(canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 8.5 * mm, footer_text[:150])
        canvas.drawRightString(PAGE_W - MARGIN, 8.5 * mm, str(document.page))
        canvas.restoreState()

    template = BaseDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                               bottomMargin=18 * mm, title=clean(f'NINA · {report["territory"]["name"]}'),
                               author="NINA", subject=clean(t["kicker"]), creator="NINA (ReportLab)")
    frame = Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - MARGIN - 18 * mm, id="body")
    template.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=decorate)])
    template.build(flow)
    return buffer.getvalue()
