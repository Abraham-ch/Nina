"""Territorial fire evidence report (docs/TERRITORIAL_REPORT.md).

Builds a decision-ready report for a territory and a month from the harmonized product and the
offline context layers in ``source/context`` (districts, INDECI emergencies, fire events, forest
loss, climate). Every figure is computed here; the summary only restates computed facts.
Sections whose layer is missing are returned with ``status="not_available"``.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any, Literal

import shapely
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import kendalltau, theilslopes
from shapely.geometry import mapping, shape

from .config import DATA, SOURCE
from .report_document import format_number
from .harmonized import (
    CLIMATOLOGY_FIRST_YEAR,
    UNIT,
    HarmonizedSelection,
    compare,
    load_json,
    month_to_date,
    monthly_calendar,
    published,
    selection_database,
)

router = APIRouter(tags=["Territorial report"])
CONTEXT = SOURCE / "context"
REPORT_VERSION = "1"
EVENT_MIN_CELL_DAYS = 5  # "significant" fire events: at least five active cell-days
SEASON_MONTHS = (7, 8, 9, 10)  # Peruvian fire season used for season totals
TREND_FIRST_YEAR = 2003
SIGNIFICANCE = 0.05


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(default="Peru", max_length=100)
    ubigeo: str | None = Field(
        default=None, pattern=r"^\d{2}(\d{2}(\d{2})?)?$", description="Peru: 2, 4 or 6 digits"
    )
    geometry: dict | None = None
    year: int = Field(ge=2002, le=2100)
    month: int = Field(ge=1, le=12)
    language: Literal["en", "es"] = "en"


# ---------------------------------------------------------------- territory


@lru_cache(maxsize=1)
def districts() -> list[tuple[dict[str, str], Any]]:
    path = CONTEXT / "districts/peru_districts.geojson"
    if not path.exists():
        return []
    return [
        (feature["properties"], shape(feature["geometry"]))
        for feature in load_json(path)["features"]
    ]


def resolve_territory(request: ReportRequest) -> dict[str, Any]:
    """Name, type and polygon (if any) of the requested territory."""
    if request.ubigeo:
        matches = [(p, g) for p, g in districts() if p["ubigeo"].startswith(request.ubigeo)]
        if not matches:
            raise HTTPException(422, "Unknown UBIGEO; the district layer is missing or the code does not exist")
        first = matches[0][0]
        level = {2: "department", 4: "province", 6: "district"}[len(request.ubigeo)]
        name = {
            "department": first["department"],
            "province": f"{first['province']} ({first['department']})",
            "district": f"{first['district']} ({first['province']}, {first['department']})",
        }[level]
        polygon = shapely.union_all([g for _, g in matches]).buffer(0)
        return {"type": level, "name": name.title(), "ubigeo": request.ubigeo, "country": "Peru",
                "polygon": polygon, "ubigeos": sorted(p["ubigeo"] for p, _ in matches)}
    if request.geometry:
        polygon = shapely.make_valid(shape(request.geometry))
        return {"type": "polygon", "name": "Custom area", "ubigeo": None, "country": request.country,
                "polygon": polygon, "ubigeos": None}
    return {"type": "country", "name": request.country, "ubigeo": None, "country": request.country,
            "polygon": None, "ubigeos": None}


def harmonized_selection(request: ReportRequest, territory: dict[str, Any]) -> HarmonizedSelection:
    """Selection for the harmonized engine; trusted polygons skip the request size limit."""
    end = max(request.year, date.today().year)
    geometry = mapping(territory["polygon"]) if territory["polygon"] is not None else None
    # Peruvian divisions are always inside Peru; a free polygon keeps the requested country
    # ("world" lets the engine drop border slivers); a country has no polygon.
    country = "Peru" if territory["ubigeo"] else request.country
    return HarmonizedSelection.model_construct(
        country=country, year_start=CLIMATOLOGY_FIRST_YEAR, year_end=end,
        selected_year=request.year, selected_month=request.month, geometry=geometry,
    )


# ---------------------------------------------------------------- sections


def trend(years: list[int], values: list[float]) -> dict[str, Any]:
    """Theil–Sen slope (% of the median per year) and Mann–Kendall p-value."""
    if len(years) < 8 or statistics.median(values) <= 0:
        return {"slope_pct_per_year": None, "p_value": None, "significant": False, "direction": "insufficient"}
    slope = theilslopes(values, years)[0] / statistics.median(values) * 100
    p_value = float(kendalltau(years, values).pvalue)
    significant = p_value < SIGNIFICANCE
    return {
        "slope_pct_per_year": round(float(slope), 2),
        "p_value": round(p_value, 4),
        "significant": significant,
        "direction": ("increase" if slope > 0 else "decrease") if significant else "no_trend",
    }


def section_current(months: list[dict], selected: dict, current: dict | None) -> dict[str, Any]:
    index = months.index(selected)
    strip = [
        {k: m[k] for k in ["year", "month", "value", "status", "anomaly_percent", "rank", "rank_of"]}
        for m in months[max(0, index - 11): index + 1]
    ]
    return {"status": "available", "month": selected, "month_to_date": current, "last_12_months": strip}


def section_history(connection, months: list[dict], year: int) -> dict[str, Any]:
    annual = connection.execute(
        """SELECT year(day) y, sum(active_harmonized), sum(pixel_rows) FROM selected_activity
        WHERE year(day) BETWEEN ? AND ? GROUP BY 1 ORDER BY 1""",
        [TREND_FIRST_YEAR, year],
    ).fetchall()
    rows = [{"year": int(y), "harmonized": float(h or 0), "raw_pixels": float(p or 0)} for y, h, p in annual]
    # The current calendar year is incomplete and never enters the trend.
    trend_end = year if year < date.today().year else date.today().year - 1
    complete = [r for r in rows if r["year"] <= trend_end]
    years = [r["year"] for r in complete]
    season = {}
    by_year: dict[int, list[dict]] = {}
    for m in months:
        if m["month"] in SEASON_MONTHS:
            by_year.setdefault(m["year"], []).append(m)
    totals = {y: sum(m["value"] for m in ms) for y, ms in by_year.items()
              if len(ms) == len(SEASON_MONTHS) and all(m["value"] is not None for m in ms)}
    if year in totals:
        history = [v for y, v in totals.items() if y != year and y < date.today().year]
        season = {"value": totals[year], "years_compared": len(history) + 1,
                  **({} if len(history) < 5 else compare(totals[year], history))}
    return {
        "status": "available" if rows else "not_available",
        "annual": rows,
        "season_jul_oct": season,
        "trend_harmonized": trend(years, [r["harmonized"] for r in complete]),
        "trend_raw_pixels": trend(years, [r["raw_pixels"] for r in complete]),
        "trend_period": [years[0], years[-1]] if years else None,
    }


def territory_ubigeos(connection, territory: dict[str, Any]) -> list[str] | None:
    """Districts covering the selected cells (Peru only)."""
    if territory["ubigeos"] is not None:
        return territory["ubigeos"]
    path = CONTEXT / "districts/cell_district.parquet"
    if not path.exists():
        return None
    rows = connection.execute(
        f"SELECT DISTINCT d.ubigeo FROM read_parquet('{path.as_posix()}') d JOIN selected_cells USING(cell)"
    ).fetchall()
    return sorted(r[0] for r in rows) or None


def section_events(connection, territory: dict[str, Any], year: int, language: str) -> dict[str, Any]:
    events_path = CONTEXT / "events/fire_events.parquet"
    members_path = CONTEXT / "events/event_cell_days.parquet"
    emergencies_path = CONTEXT / "indeci/forest_fire_emergencies.parquet"
    if not events_path.exists() or not members_path.exists():
        return {"status": "not_available", "reason": "fire event layer not built"}
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE territory_events AS
        SELECT e.* FROM read_parquet('{events_path.as_posix()}') e
        WHERE e.event_id IN (SELECT DISTINCT m.event_id FROM read_parquet('{members_path.as_posix()}') m
                             JOIN selected_cells USING(cell))""")
    detected = {
        int(y): (int(a), int(b))
        for y, a, b in connection.execute(
            f"""SELECT year(start_day), count(*), count(*) FILTER(WHERE cell_days >= {EVENT_MIN_CELL_DAYS})
            FROM territory_events WHERE era = 'viirs' GROUP BY 1"""
        ).fetchall()
    }
    ubigeos = territory_ubigeos(connection, territory)
    reported: dict[int, int] = {}
    top: list[dict] = []
    coverage: tuple[date, date] | None = None
    if emergencies_path.exists():
        first, last = connection.execute(
            f"SELECT min(day), max(day) FROM read_parquet('{emergencies_path.as_posix()}')"
        ).fetchone()
        coverage = (first, last)
    if ubigeos and emergencies_path.exists():
        connection.execute("CREATE OR REPLACE TEMP TABLE territory_ubigeo(ubigeo VARCHAR)")
        connection.executemany("INSERT INTO territory_ubigeo VALUES (?)", [(u,) for u in ubigeos])
        # INDECI also uses districts created after the boundary layer: match by code prefix for a
        # Peruvian division and take every record for the whole country.
        if territory["type"] == "country":
            in_territory = "true"
        elif territory["ubigeo"]:
            in_territory = f"starts_with(ubigeo, '{territory['ubigeo']}')"
        else:
            in_territory = "ubigeo IN (SELECT ubigeo FROM territory_ubigeo)"
        reported = {
            int(y): int(n)
            for y, n in connection.execute(
                f"""SELECT year, count(*) FROM read_parquet('{emergencies_path.as_posix()}')
                WHERE {in_territory} GROUP BY 1"""
            ).fetchall()
        }
        names = {p["ubigeo"]: p for p, _ in districts()}
        # One level below the territory: country → departments, department → provinces, else districts.
        level = {"country": 2, "department": 4, "polygon": 4}.get(territory["type"], 6)
        inside = f"starts_with(code, '{territory['ubigeo']}')" if territory["ubigeo"] else "true"
        rows = connection.execute(
            f"""WITH ev AS (SELECT substr(ubigeo, 1, {level}) code, count(*) n FROM territory_events
                    WHERE era='viirs' AND year(start_day)=? AND cell_days >= {EVENT_MIN_CELL_DAYS}
                    AND ubigeo IS NOT NULL GROUP BY 1),
                em AS (SELECT substr(ubigeo, 1, {level}) code, count(*) n
                    FROM read_parquet('{emergencies_path.as_posix()}')
                    WHERE year=? AND {in_territory} GROUP BY 1)
            SELECT coalesce(ev.code, em.code) code, coalesce(ev.n, 0), coalesce(em.n, 0)
            FROM ev FULL JOIN em USING(code)
            WHERE {inside} ORDER BY 2 DESC, 3 DESC LIMIT 12""",
            [year, year],
        ).fetchall()
        for code, events, emergencies in rows:
            sample = next((p for u, p in names.items() if u.startswith(code)), None)
            label = code
            if sample:
                label = {2: sample["department"], 4: sample["province"], 6: sample["district"]}[level].title()
            top.append({"code": code, "name": label, "events": events, "emergencies": emergencies})
    years = sorted(set(detected) | set(reported))
    def emergencies_in(year_: int) -> int | None:
        """0 is a real zero only inside the INDECI coverage; outside it there is no record."""
        if not ubigeos or coverage is None or not coverage[0].year <= year_ <= coverage[1].year:
            return None
        return reported.get(year_, 0)

    by_year = [
        {"year": y, "events": detected.get(y, (0, 0))[0], "significant_events": detected.get(y, (0, 0))[1],
         "emergencies": emergencies_in(y)}
        for y in years if y >= 2012
    ]
    selected = next((r for r in by_year if r["year"] == year), None)
    return {
        "status": "available",
        "rule": "events: harmonized cell-days joined across neighbouring cells and gaps of at most 2 days; "
        f"significant = at least {EVENT_MIN_CELL_DAYS} active cell-days; VIIRS era only (from 2012)",
        "emergencies_source": "INDECI/SINPAD forest-fire emergencies (registered emergencies, not every fire)"
        if ubigeos else None,
        "emergencies_coverage": [str(coverage[0])[:10], str(coverage[1])[:10]] if coverage and ubigeos else None,
        "selected_year": selected,
        "by_year": by_year,
        "top_subdivisions": top,
    }


def territory_cells_all(connection, territory: dict[str, Any]) -> str | None:
    """Every H3 cell of the territory (not only cells that ever burned), for forest statistics."""
    path = CONTEXT / "districts/cell_district.parquet"
    if territory["ubigeos"] is not None and path.exists():
        connection.execute("CREATE OR REPLACE TEMP TABLE all_cells(cell VARCHAR)")
        connection.execute(
            f"INSERT INTO all_cells SELECT cell FROM read_parquet('{path.as_posix()}') WHERE ubigeo IN "
            f"(SELECT unnest(?::VARCHAR[]))",
            [territory["ubigeos"]],
        )
        return "all_cells"
    if territory["type"] == "country" and territory["country"] == "Peru" and path.exists():
        connection.execute(
            f"CREATE OR REPLACE TEMP TABLE all_cells AS SELECT cell FROM read_parquet('{path.as_posix()}')"
        )
        return "all_cells"
    return None


def section_forest(connection, territory: dict[str, Any], year: int) -> dict[str, Any]:
    loss_path = CONTEXT / "forest_loss/forest_loss_cell_year.parquet"
    forest_path = CONTEXT / "forest_loss/forest_2000_cell.parquet"
    if not loss_path.exists():
        return {"status": "not_available", "reason": "forest loss layer not built"}
    cells = territory_cells_all(connection, territory) or "selected_cells"
    connection.execute("""CREATE OR REPLACE TEMP TABLE fire_cell_year AS
        SELECT DISTINCT cell, year(day) AS year FROM selected_activity""")
    rows = connection.execute(
        f"""SELECT l.year, sum(l.loss_ha),
            sum(l.loss_ha) FILTER(WHERE EXISTS(SELECT 1 FROM fire_cell_year f WHERE f.cell=l.cell
                AND f.year BETWEEN l.year-1 AND l.year))
        FROM read_parquet('{loss_path.as_posix()}') l WHERE l.cell IN (SELECT cell FROM {cells})
        GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    forest_2000 = None
    if forest_path.exists():
        forest_2000 = connection.execute(
            f"SELECT sum(forest_2000_ha) FROM read_parquet('{forest_path.as_posix()}') "
            f"WHERE cell IN (SELECT cell FROM {cells})"
        ).fetchone()[0]
    by_year = [{"year": int(y), "loss_ha": float(t or 0), "loss_ha_with_fire": float(f or 0)} for y, t, f in rows]
    selected = next((r for r in by_year if r["year"] == year), None)
    manifest = load_json(CONTEXT / "forest_loss/manifest.json") if (CONTEXT / "forest_loss/manifest.json").exists() else {}
    return {
        "status": "available" if by_year else "not_available",
        "definition": "tree-cover loss (Hansen/UMD, canopy >= 30 % in 2000); 'with fire' = cell with "
        "satellite fire activity in the same or the previous year",
        "source_version": manifest.get("version") or manifest.get("source_version"),
        "forest_2000_ha": forest_2000,
        "selected_year": selected,
        "last_year_available": by_year[-1]["year"] if by_year else None,
        "by_year": by_year,
    }


def section_climate(territory: dict[str, Any], year: int, month: int, connection) -> dict[str, Any]:
    path = CONTEXT / "climate/climate_department_month.parquet"
    if not path.exists():
        return {"status": "not_available", "reason": "climate layer not built"}
    ubigeos = territory["ubigeos"] or territory_ubigeos(connection, territory) or []
    names = {p["ubigeo"][:2]: p["department"] for p, _ in districts()}
    keys = sorted({_key(names[u[:2]]) for u in ubigeos if u[:2] in names})
    if not keys:
        return {"status": "not_available", "reason": "climate is available for Peruvian departments only"}
    rows = connection.execute(
        f"""SELECT department, month, precip_mm, precip_z, vpd_kpa, vpd_z, drought
        FROM read_parquet('{path.as_posix()}') WHERE year=? AND department_key IN (SELECT unnest(?::VARCHAR[]))
        ORDER BY department, month""",
        [year, keys],
    ).fetchall()
    selected = [
        {"department": d, "precip_mm": p, "precip_z": pz, "vpd_kpa": v, "vpd_z": vz, "drought": bool(dr)}
        for d, m, p, pz, v, vz, dr in rows if m == month
    ]
    season = {}
    for d, m, _, pz, _, vz, dr in rows:
        if m in SEASON_MONTHS:
            season.setdefault(d, []).append((pz, vz, dr))
    season_summary = [
        {"department": d, "precip_z_mean": statistics.fmean(x[0] for x in v),
         "vpd_z_mean": statistics.fmean(x[1] for x in v), "drought_months": sum(bool(x[2]) for x in v)}
        for d, v in season.items()
    ]
    return {
        "status": "available" if selected else "not_available",
        "source": "NASA POWER (monthly, ~0.5 degree); anomalies vs 2002–2024 climatology",
        "note": "Context only: no causal attribution of fire activity.",
        "selected_month": selected,
        "season_jul_oct": season_summary,
    }


def _key(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


def section_quality(selected: dict, manifest: dict) -> dict[str, Any]:
    return {
        "status": "available",
        "valid_region_days": selected["valid_region_days"],
        "expected_region_days": selected["expected_region_days"],
        "noaa20_filled_days": selected.get("noaa20_filled_days", 0),
        "unvalidated_share": selected.get("unvalidated_share", 0.0),
        "is_provisional": selected["is_provisional"],
        "validation_status": "validated" if manifest["status"] == "published" else "experimental",
        "gates": manifest["gates"],
        "typical_yearly_error": "about ±10 % in the MODIS era (median 6 % in validated strata)",
        "disclaimer": manifest["legal"],
    }


# ---------------------------------------------------------------- summary

TEXT = {
    "en": {
        "current": "{period}: {value} VIIRS-equivalent active cell-days, {anomaly} % against the median of {n} other years (rank {rank} of {rank_of}).",
        "current_none": "{period}: no comparable value yet ({status}).",
        "mtd": "Month to date ({days} valid days through day {through}): {value} against a median of {median} for the same days.",
        "season": "Fire season (Jul–Oct) {year}: rank {rank} of {rank_of}, {anomaly} % against the median.",
        "trend": "Trend {start}–{end}: {harm}. Without harmonization the raw series would show {raw}.",
        "trend_words": {"increase": "a significant increase ({slope} %/year)", "decrease": "a significant decrease ({slope} %/year)",
                        "no_trend": "no significant trend", "insufficient": "too few years"},
        "events": "{year}: {events} significant fire events detected by satellite; {emergencies} forest-fire emergencies registered by INDECI.",
        "events_only": "{year}: {events} significant fire events detected by satellite.",
        "indeci_partial": " (INDECI records available through {through}.)",
        "forest": "Tree-cover loss {year}: {loss} ha, of which {fire} ha in cells with fire activity.",
        "climate": "Climate {period}: {drought} of {total} department(s) under drought conditions (low precipitation and high vapour-pressure deficit).",
    },
    "es": {
        "current": "{period}: {value} celdas-día activas equivalentes VIIRS, {anomaly} % respecto de la mediana de otros {n} años (puesto {rank} de {rank_of}).",
        "current_none": "{period}: aún sin valor comparable ({status}).",
        "mtd": "Mes en curso ({days} días válidos hasta el día {through}): {value} frente a una mediana de {median} para los mismos días.",
        "season": "Temporada de incendios (jul–oct) {year}: puesto {rank} de {rank_of}, {anomaly} % respecto de la mediana.",
        "trend": "Tendencia {start}–{end}: {harm}. Sin armonización, la serie cruda mostraría {raw}.",
        "trend_words": {"increase": "un aumento significativo ({slope} %/año)", "decrease": "una disminución significativa ({slope} %/año)",
                        "no_trend": "ninguna tendencia significativa", "insufficient": "años insuficientes"},
        "events": "{year}: {events} evento(s) de incendio significativo(s) detectado(s) por satélite; {emergencies} emergencia(s) por incendio forestal registrada(s) por INDECI.",
        "events_only": "{year}: {events} evento(s) de incendio significativo(s) detectado(s) por satélite.",
        "indeci_partial": " (registros de INDECI disponibles hasta {through}).",
        "forest": "Pérdida de cobertura arbórea {year}: {loss} ha, de las cuales {fire} ha en celdas con actividad de fuego.",
        "climate": "Clima {period}: {drought} de {total} departamento(s) en condición de sequía (baja precipitación y alto déficit de presión de vapor).",
    },
}


def summary(report: dict[str, Any]) -> list[str]:
    language = report["language"]
    t = TEXT[language]

    def n(value: Any, digits: int = 0, sign: bool = False) -> str:
        return format_number(value, language, digits, sign)

    s = report["sections"]
    period = f"{report['period']['year']}-{report['period']['month']:02d}"
    lines = []
    month = s["current"]["month"]
    if month["value"] is not None and month["anomaly_percent"] is not None:
        lines.append(t["current"].format(period=period, value=n(month["value"]), anomaly=n(month["anomaly_percent"], sign=True),
                                         n=month["historical_n"], rank=month["rank"], rank_of=month["rank_of"]))
    else:
        lines.append(t["current_none"].format(period=period, status=month["status"]))
    mtd = s["current"]["month_to_date"]
    if mtd and mtd["value"] is not None and mtd["historical_median"] is not None:
        lines.append(t["mtd"].format(days=mtd["valid_days"], through=mtd["through_day"], value=n(mtd["value"]),
                                     median=n(mtd["historical_median"])))
    season = s["history"].get("season_jul_oct") or {}
    if season.get("anomaly_percent") is not None:
        lines.append(t["season"].format(year=report["period"]["year"], rank=season["rank"],
                                        rank_of=season["rank_of"], anomaly=n(season["anomaly_percent"], sign=True)))
    h = s["history"]
    if h.get("trend_period"):
        words = t["trend_words"]
        lines.append(t["trend"].format(
            start=h["trend_period"][0], end=h["trend_period"][1],
            harm=words[h["trend_harmonized"]["direction"]].format(slope=n(h["trend_harmonized"]["slope_pct_per_year"] or 0, 1, True)),
            raw=words[h["trend_raw_pixels"]["direction"]].format(slope=n(h["trend_raw_pixels"]["slope_pct_per_year"] or 0, 1, True)),
        ))
    ev = s["events"]
    if ev["status"] == "available" and ev.get("selected_year"):
        row = ev["selected_year"]
        if row["emergencies"] is not None:
            line = t["events"].format(year=row["year"], events=n(row["significant_events"]), emergencies=n(row["emergencies"]))
            through = (ev.get("emergencies_coverage") or [None, None])[1]
            if through and int(through[:4]) == row["year"] and through[5:] != "12-31":
                line += t["indeci_partial"].format(through=through)
            lines.append(line)
        else:
            lines.append(t["events_only"].format(year=row["year"], events=n(row["significant_events"])))
    fo = s["forest"]
    if fo["status"] == "available" and fo.get("selected_year"):
        lines.append(t["forest"].format(year=fo["selected_year"]["year"], loss=n(fo["selected_year"]["loss_ha"]),
                                        fire=n(fo["selected_year"]["loss_ha_with_fire"])))
    cl = s["climate"]
    if cl["status"] == "available":
        lines.append(t["climate"].format(period=period, drought=sum(r["drought"] for r in cl["selected_month"]),
                                         total=len(cl["selected_month"])))
    return lines


# ---------------------------------------------------------------- endpoints


def build_report(request: ReportRequest) -> dict[str, Any]:
    manifest, folder = published()
    territory = resolve_territory(request)
    selection = harmonized_selection(request, territory)
    as_of_year = int(manifest["as_of_date"][:4]) if manifest.get("as_of_date") else None
    with selection_database(selection, folder) as (connection, number_countries, excluded):
        cells = connection.execute("SELECT count(*) FROM selected_cells").fetchone()[0]
        months = monthly_calendar(connection, selection, number_countries, as_of_year=as_of_year)
        selected = next(m for m in months if (m["year"], m["month"]) == (request.year, request.month))
        current = None
        if selected["value"] is None and selected["valid_region_days"] > 0 and not selected["data_gap"]:
            current = month_to_date(connection, selection, number_countries, as_of_year=as_of_year)
        sections = {
            "current": section_current(months, selected, current),
            "history": section_history(connection, months, request.year),
            "events": section_events(connection, territory, request.year, request.language),
            "forest": section_forest(connection, territory, request.year),
            "climate": section_climate(territory, request.year, request.month, connection),
            "quality": section_quality(selected, manifest),
        }
    payload = {"request": request.model_dump(), "dataset_id": manifest["id"], "version": REPORT_VERSION}
    identifier = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
    report = {
        "id": identifier,
        "version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "language": request.language,
        "territory": {k: v for k, v in territory.items() if k not in {"polygon", "ubigeos"}}
        | {"cells": cells, "excluded_border_countries": excluded},
        "period": {"year": request.year, "month": request.month},
        "unit": UNIT,
        "dataset_id": manifest["id"],
        "method_version": manifest["method_version"],
        "validation_status": "validated" if manifest["status"] == "published" else "experimental",
        "sections": sections,
        "references": manifest["references"],
        "legal": manifest["legal"],
        "request": request.model_dump(),
    }
    report["summary"] = summary(report)
    report["summary_mode"] = "template"
    cache = DATA / "jobs/reports"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{identifier}.json").write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    return report


@router.post("/api/reports/territorial")
def create_report(request: ReportRequest) -> dict[str, Any]:
    return build_report(request)


def stored(identifier: str) -> dict[str, Any]:
    path = DATA / "jobs/reports" / f"{identifier}.json"
    if len(identifier) != 24 or not identifier.isalnum() or not path.exists():
        raise HTTPException(404, "Report not found")
    return load_json(path)


@router.get("/api/reports/territorial/{identifier}")
def get_report(identifier: str) -> dict[str, Any]:
    return stored(identifier)


@router.get("/api/reports/territorial/{identifier}/document", response_class=HTMLResponse)
def report_document(identifier: str) -> HTMLResponse:
    from .report_document import render

    return HTMLResponse(render(stored(identifier)))
