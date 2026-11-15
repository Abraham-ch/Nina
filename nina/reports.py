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
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import shapely
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import kendalltau, theilslopes
from shapely.geometry import mapping, shape

from .config import DATA, ROOT, SOURCE
from .report_document import format_number
from .harmonized import (
    CLIMATOLOGY_FIRST_YEAR,
    UNIT,
    HarmonizedSelection,
    compare,
    country_shapes,
    countries_path,
    load_json,
    month_to_date,
    monthly_calendar,
    published,
    selection_database,
)

router = APIRouter(tags=["Territorial report"])
CONTEXT = SOURCE / "context"
REPORT_VERSION = "4"  # 4: case study in Spanish; 2: burned area (MCD64A1 via GWIS); 3: 30 m burned-area case study
EVENT_MIN_CELL_DAYS = 5  # "significant" fire events: at least five active cell-days
SEASON_MONTHS = (7, 8, 9, 10)  # Peruvian fire season used for season totals
TREND_FIRST_YEAR = 2003
SIGNIFICANCE = 0.05
DRY_MONTH_MM = 10.0  # below this normal monthly rainfall a drought flag is not meaningful
# INEI department names → geoBoundaries ADM1 keys used by the climate layer.
CLIMATE_ALIASES = {"CALLAO": ["EL CALLAO"], "LIMA": ["LIMA", "MUNICIPALIDAD METROPOLITANA DE LIMA"]}


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(default="Peru", max_length=100)
    ubigeo: str | None = Field(
        default=None, pattern=r"^\d{2}(\d{2}(\d{2})?)?$", description="Peru: 2, 4 or 6 digits"
    )
    geometry: dict | None = None
    place_name: str | None = Field(default=None, max_length=120, description="Name shown for a polygon; "
                                   "a Peruvian department name is resolved to its UBIGEO")
    year: int = Field(ge=2002, le=2100)
    month: int = Field(ge=1, le=12)
    language: Literal["en", "es"] = "en"


# ---------------------------------------------------------------- territory

# INEI writes names in capitals without accents; departments are shown with their usual spelling.
DEPARTMENT_NAMES = {
    "ANCASH": "Áncash", "APURIMAC": "Apurímac", "HUANUCO": "Huánuco", "JUNIN": "Junín",
    "SAN MARTIN": "San Martín", "MADRE DE DIOS": "Madre de Dios", "LA LIBERTAD": "La Libertad",
}
LOWER_WORDS = {"de", "del", "la", "las", "los", "y", "el"}


def display_name(name: str) -> str:
    """'MADRE DE DIOS' -> 'Madre de Dios'; known departments keep their accents."""
    key = _key(name)
    if key in DEPARTMENT_NAMES:
        return DEPARTMENT_NAMES[key]
    words = name.strip().lower().split()
    return " ".join(w if i and w in LOWER_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


@lru_cache(maxsize=1)
def districts() -> list[tuple[dict[str, str], Any]]:
    path = CONTEXT / "districts/peru_districts.geojson"
    if not path.exists():
        return []
    return [
        (feature["properties"], shape(feature["geometry"]))
        for feature in load_json(path)["features"]
    ]


def department_code(name: str | None) -> str | None:
    """INEI department code for a department name (accents and the 'El'/'Region' prefixes ignored).

    geoBoundaries keeps Lima Metropolitana and Lima Provincias apart; INEI's Lima (15) includes both,
    so those two names are not resolved and keep their own outline.
    """
    key = _key(name or "").removeprefix("REGION ").removeprefix("EL ")
    codes = {_key(p["department"]): p["ubigeo"][:2] for p, _ in districts()}
    if key in {"LIMA", "MUNICIPALIDAD METROPOLITANA DE LIMA"}:
        return None
    return codes.get(key)


def resolve_territory(request: ReportRequest) -> dict[str, Any]:
    """Name, type and polygon (if any) of the requested territory."""
    if not request.ubigeo and request.place_name and request.country == "Peru":
        code = department_code(request.place_name)
        if code:
            request = request.model_copy(update={"ubigeo": code})
    if request.ubigeo:
        matches = [(p, g) for p, g in districts() if p["ubigeo"].startswith(request.ubigeo)]
        if not matches:
            raise HTTPException(422, "Unknown UBIGEO; the district layer is missing or the code does not exist")
        first = matches[0][0]
        level = {2: "department", 4: "province", 6: "district"}[len(request.ubigeo)]
        department, province = display_name(first["department"]), display_name(first["province"])
        name = {
            "department": department,
            "province": f"{province} ({department})",
            "district": f"{display_name(first['district'])} ({province}, {department})",
        }[level]
        polygon = shapely.union_all([g for _, g in matches]).buffer(0)
        return {"type": level, "name": name, "ubigeo": request.ubigeo, "country": "Peru",
                "polygon": polygon, "ubigeos": sorted(p["ubigeo"] for p, _ in matches)}
    if request.geometry:
        polygon = shapely.make_valid(shape(request.geometry))
        return {"type": "polygon", "name": request.place_name or "Custom area", "ubigeo": None,
                "country": request.country,
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
    """Theil–Sen slope (% of the median per year), its line, and the Mann–Kendall p-value."""
    if len(years) < 8 or statistics.median(values) <= 0:
        return {"slope_pct_per_year": None, "p_value": None, "significant": False, "direction": "insufficient",
                "line": None}
    fit = theilslopes(values, years)
    slope = fit[0] / statistics.median(values) * 100
    p_value = float(kendalltau(years, values).pvalue)
    significant = p_value < SIGNIFICANCE
    return {
        "slope_pct_per_year": round(float(slope), 2),
        "p_value": round(p_value, 4),
        "significant": significant,
        "direction": ("increase" if slope > 0 else "decrease") if significant else "no_trend",
        "line": {"slope": float(fit[0]), "intercept": float(fit[1])},
    }


def seasonal_profile(months: list[dict], year: int) -> list[dict[str, Any]]:
    """For each calendar month: the selected year's value and the band of the other eligible years."""
    profile = []
    for month in range(1, 13):
        history = [m["value"] for m in months if m["month"] == month and m["year"] != year
                   and m["eligible_for_climatology"]]
        this = next((m for m in months if (m["year"], m["month"]) == (year, month)), None)
        band = statistics.quantiles(history, n=10, method="inclusive") if len(history) >= 2 else None
        profile.append({
            "month": month,
            "value": this["value"] if this else None,
            "status": this["status"] if this else "not_available",
            "median": statistics.median(history) if history else None,
            "p10": band[0] if band else None,
            "p90": band[-1] if band else None,
            "years": len(history),
        })
    return profile


def section_current(months: list[dict], selected: dict, current: dict | None, year: int) -> dict[str, Any]:
    index = months.index(selected)
    strip = [
        {k: m[k] for k in ["year", "month", "value", "status", "anomaly_percent", "rank", "rank_of"]}
        for m in months[max(0, index - 11): index + 1]
    ]
    calendar_matrix = [
        {k: m[k] for k in ["year", "month", "value", "status", "anomaly_percent"]} for m in months
    ]
    return {"status": "available", "month": selected, "month_to_date": current, "last_12_months": strip,
            "profile": seasonal_profile(months, year), "calendar": calendar_matrix}


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
    # Another country's border cells can touch Peruvian districts: only Peruvian territories use INDECI.
    path = CONTEXT / "districts/cell_district.parquet"
    if territory["country"] != "Peru" or not path.exists():
        return None
    rows = connection.execute(
        f"SELECT DISTINCT d.ubigeo FROM read_parquet('{path.as_posix()}') d JOIN selected_cells USING(cell)"
    ).fetchall()
    return sorted(r[0] for r in rows) or None


# Registered fire emergencies/incidents outside Peru: point records in source/context/registries/<file>.parquet
# (record_id, day, year, latitude, longitude, size_ha) with a manifest giving the registry name.
POINT_REGISTRIES = {
    "United States of America": "usa_nifc", "Brazil": "brazil_ibama_roi", "Indonesia": "indonesia_bnpb",
    "Australia": "australia", "Canada": "canada_cnfdb", "Portugal": "portugal_icnf",
}
EVENT_VALIDATIONS = {"Peru": "events_peru_indeci", "United States of America": "events_usa_nifc",
                     "Brazil": "events_brazil_ibama_roi", "Indonesia": "events_indonesia_bnpb",
                     "Australia": "events_australia", "Canada": "events_canada_cnfdb",
                     "Portugal": "events_portugal_icnf"}
REGISTRY_LABELS = {
    "Peru": {"en": "INDECI emergencies", "es": "Emergencias INDECI"},
    "usa_nifc": {"en": "Reported wildfires ≥ 40 ha (NIFC)", "es": "Incendios reportados ≥ 40 ha (NIFC)"},
    "brazil_ibama_roi": {"en": "Federal brigade fire records (IBAMA)", "es": "Incendios atendidos por brigadas (IBAMA)"},
    "indonesia_bnpb": {"en": "BNPB forest and land fire records", "es": "Registros BNPB de incendios forestales"},
    "australia": {"en": "Mapped bushfires (Geoscience Australia)", "es": "Incendios cartografiados (Geoscience Australia)"},
    "canada_cnfdb": {"en": "Agency fire reports ≥ 40 ha (CNFDB)", "es": "Incendios reportados ≥ 40 ha (CNFDB)"},
    "portugal_icnf": {"en": "Rural fire records ≥ 40 ha (ICNF)", "es": "Incendios rurales registrados ≥ 40 ha (ICNF)"},
}


def cross_check(name: str, territory: dict[str, Any]) -> dict[str, Any] | None:
    """National headline of a cross-source comparison, plus the territory's department when present."""
    validation = validation_file(name)
    if not validation or territory["country"] != "Peru" or "headline" not in validation:
        return None
    result = dict(validation["headline"])
    code = (territory.get("ubigeo") or "")[:2]
    department = next((d for d in validation.get("by_department", []) if code and d.get("department_code") == code), None)
    if department:
        result["department"] = department
    return result


def validation_file(name: str) -> dict[str, Any] | None:
    path = CONTEXT / "validation" / f"{name}.json"
    return load_json(path) if path.exists() else None


def events_validation(territory: dict[str, Any]) -> dict[str, Any] | None:
    """Headline of the events-vs-registry validation for the territory's country (and its department)."""
    validation = validation_file(EVENT_VALIDATIONS.get(territory["country"], ""))
    if not validation or "headline" not in validation:
        return None
    result = dict(validation["headline"])
    # A match means little where fire is detected almost every week anyway (large or fire-prone units).
    result["informative"] = (result["rate"] - result["chance_rate"]) >= 0.10 and result["chance_rate"] < 0.80
    code = (territory.get("ubigeo") or "")[:2]
    department = next((d for d in validation.get("by_department", []) if code and d.get("department_code") == code), None)
    if department and department.get("records", 0) >= 20:
        result["department"] = {k: department[k] for k in ("department", "records", "rate", "chance_rate") if k in department}
    return result


def point_registry(country: str):
    """(columns as NumPy arrays, manifest) of the country's point registry, or (None, None)."""
    import duckdb

    name = POINT_REGISTRIES.get(country)
    if not name:
        return None, None
    path = CONTEXT / "registries" / f"{name}.parquet"
    if not path.exists():
        return None, None
    manifest_path = CONTEXT / "registries" / f"{name}.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {"name": name}
    minimum = float(manifest.get("min_size_ha") or 0)
    where = f"WHERE coalesce(size_ha, 0) >= {minimum}" if minimum > 0 else ""
    with duckdb.connect() as connection:
        columns = connection.execute(
            f"SELECT year, latitude, longitude, day::DATE AS day FROM read_parquet('{path.as_posix()}') {where}"
        ).fetchnumpy()
    return columns, manifest


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
                label = display_name({2: sample["department"], 4: sample["province"], 6: sample["district"]}[level])
            top.append({"code": code, "name": label, "events": events, "emergencies": emergencies})
    registry_name, registry_label = None, None
    if ubigeos and emergencies_path.exists():
        registry_name = "INDECI/SINPAD forest-fire emergencies (registered emergencies, not every fire)"
        registry_label = REGISTRY_LABELS["Peru"][language]
    elif not ubigeos:
        records, manifest = point_registry(territory["country"])
        if records is not None and len(records["year"]):
            import numpy as np

            keep = np.ones(len(records["year"]), dtype=bool)
            if territory["polygon"] is not None:
                keep = shapely.contains_xy(territory["polygon"], records["longitude"], records["latitude"])
            first, last = manifest.get("coverage") or [str(records["day"].min())[:10], str(records["day"].max())[:10]]
            coverage = (date.fromisoformat(first[:10]), date.fromisoformat(last[:10]))
            years_found, counts = np.unique(records["year"][keep], return_counts=True)
            reported = {int(y): int(n) for y, n in zip(years_found, counts, strict=True)}
            registry_name = manifest.get("source_name") or manifest.get("name")
            registry_label = REGISTRY_LABELS.get(POINT_REGISTRIES[territory["country"]], {}).get(language, registry_name)
    years = sorted(set(detected) | set(reported))
    def emergencies_in(year_: int) -> int | None:
        """0 is a real zero only inside the registry coverage; outside it there is no record."""
        if registry_name is None or coverage is None or not coverage[0].year <= year_ <= coverage[1].year:
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
        "emergencies_source": registry_name,
        "emergencies_label": registry_label,
        "emergencies_coverage": [str(coverage[0])[:10], str(coverage[1])[:10]] if coverage and registry_name else None,
        "validation": events_validation(territory),
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


# Natural Earth names that differ from the GWIS/GADM country names of the burned-area table.
GWIS_ISO3 = {
    "Bosnia and Herz.": "BIH", "Central African Rep.": "CAF", "Congo": "COG", "Czechia": "CZE",
    "Dem. Rep. Congo": "COD", "Dominican Rep.": "DOM", "Eq. Guinea": "GNQ", "N. Cyprus": "XNC",
    "Palestine": "PSE", "S. Sudan": "SSD", "Solomon Is.": "SLB", "United States of America": "USA",
    "W. Sahara": "ESH", "eSwatini": "SWZ",
}
# INEI department → GADM level-1 units (GADM splits Lima region and Lima province).
GADM_PERU = {"LIMA": ["Lima", "Lima Province"]}


def section_burned_area(connection, territory: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    """Monthly burned area (MODIS MCD64A1 c6.1, aggregated by GWIS) for a country or a Peruvian department."""
    path = CONTEXT / "burned_area/gwis_mcd64a1_admin1.parquet"
    if not path.exists():
        return {"status": "not_available", "reason": "burned area layer not built"}
    source = path.as_posix()
    scope, unit = "country", territory["name"]
    if territory["type"] == "polygon":
        return {"status": "not_available",
                "reason": "burned-area statistics are published by country and first-level unit, not for drawn areas"}
    if territory.get("ubigeo"):
        code = territory["ubigeo"][:2]
        department = next((p["department"] for p, _ in districts() if p["ubigeo"].startswith(code)), None)
        if department is None:
            return {"status": "not_available", "reason": "unknown department"}
        key = unicodedata_fold(department)
        regions = [r for (r,) in connection.execute(
            f"SELECT DISTINCT region FROM read_parquet('{source}') WHERE iso3='PER'").fetchall()]
        names = GADM_PERU.get(key) or [r for r in regions if unicodedata_fold(r) == key]
        if not names:
            return {"status": "not_available", "reason": f"no burned-area unit for {department}"}
        where, args = "iso3='PER' AND region IN (SELECT unnest(?::VARCHAR[]))", [names]
        scope, unit = "department", display_name(department)
    else:
        countries = connection.execute(f"SELECT DISTINCT iso3, country FROM read_parquet('{source}')").fetchall()
        iso3 = GWIS_ISO3.get(territory["country"]) or next(
            (i for i, c in countries if c == territory["country"]), None)
        if iso3 is None:
            return {"status": "not_available", "reason": f"no burned-area statistics for {territory['country']}"}
        where, args = "iso3=?", [iso3]
    rows = connection.execute(
        f"""SELECT year, month, sum(burned_ha), sum(forest), sum(savannas), sum(shrublands_grasslands),
            sum(croplands), sum(other) FROM read_parquet('{source}') WHERE {where} GROUP BY 1, 2 ORDER BY 1, 2""",
        args,
    ).fetchall()
    if not rows:
        return {"status": "not_available", "reason": "no burned-area rows for this territory"}
    monthly = {(int(y), int(m)): float(v or 0) for y, m, v, *_ in rows}
    yearly: dict[int, float] = {}
    classes: dict[int, dict[str, float]] = {}
    names = ["forest", "savannas", "shrublands_grasslands", "croplands", "other"]
    for y, _m, v, *parts in rows:
        yearly[int(y)] = yearly.get(int(y), 0.0) + float(v or 0)
        bucket = classes.setdefault(int(y), dict.fromkeys(names, 0.0))
        for name, part in zip(names, parts, strict=True):
            bucket[name] += float(part or 0)
    last_year, last_month = max(monthly)
    selected = None
    if (year, month) in monthly:
        value = monthly[(year, month)]
        history = [v for (y, m), v in monthly.items() if m == month and y != year]
        median = statistics.median(history) if history else None
        same_month = sorted((v for (y, m), v in monthly.items() if m == month), reverse=True)
        selected = {"year": year, "month": month, "burned_ha": value, "median_other_years_ha": median,
                    "anomaly_percent": 100 * (value / median - 1) if median else None,
                    "rank": same_month.index(value) + 1, "rank_of": len(same_month)}
    manifest_path = CONTEXT / "burned_area/gwis_mcd64a1_admin1.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    return {
        "status": "available",
        "scope": scope,
        "unit": unit,
        "source": "MODIS MCD64A1 collection 6.1 burned area (500 m), aggregated by GWIS (JRC/Copernicus); CC BY 4.0",
        "note": "Independent of the hotspots NINA harmonizes; fires much smaller than one 500 m pixel (~25 ha) are "
                "often missed." + (" Shown for the department: the table is published by first-level unit."
                                   if territory["type"] in {"province", "district"} else ""),
        "coverage": [f"{min(monthly)[0]}-{min(monthly)[1]:02d}", f"{last_year}-{last_month:02d}"],
        "by_year": [{"year": y, "burned_ha": v} for y, v in sorted(yearly.items())],
        "selected_month": selected,
        "selected_year": {"year": year, "burned_ha": yearly[year], "by_class": classes[year]} if year in yearly else None,
        "license": manifest.get("license"),
        "retrieved": manifest.get("retrieved"),
    }


def unicodedata_fold(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(plain.upper().replace("-", " ").split())


# Natural Earth names that differ from the Global Forest Watch (GADM) country names.
GFW_NAMES = {
    "United States of America": "United States", "Dem. Rep. Congo": "Democratic Republic of the Congo",
    "Congo": "Republic of the Congo", "Central African Rep.": "Central African Republic",
    "Bosnia and Herz.": "Bosnia and Herzegovina", "Dominican Rep.": "Dominican Republic",
    "Eq. Guinea": "Equatorial Guinea", "S. Sudan": "South Sudan", "Solomon Is.": "Solomon Islands",
    "eSwatini": "Swaziland", "N. Cyprus": "NorthernCyprus", "Mexico": "México",
}


CASE_FIGURES = ("prithvi_vs_dnbr_zoom.png", "post_truecolour_zoom.png", "dnbr_classes_zoom.png")


def section_burn_case(territory: dict[str, Any], year: int, month: int, language: str = "en") -> dict[str, Any]:
    """Burned area mapped at 30 m for the documented case study (Chilecito, July 2026), when the report's territory
    and period overlap it. Figures come from source/context/burn_case/summary.json (docs/BURN_CASE_CHILECITO.md)."""
    path = CONTEXT / "burn_case/summary.json"
    if not path.exists():
        return {"status": "not_available", "reason": "no 30 m burned-area case study built"}
    summary = load_json(path)
    west, south, east, north = summary["hls"]["aoi"]["analysis_wgs84"]
    first, last = summary["case"]["event_window"]
    in_period = int(first[:4]) * 100 + int(first[5:7]) <= year * 100 + month <= int(last[:4]) * 100 + int(last[5:7])
    polygon = territory.get("polygon")
    if not in_period or polygon is None or not polygon.intersects(shapely.box(west, south, east, north)):
        return {"status": "not_available", "reason": "the 30 m case study covers Chilecito (Argentina), July–August 2026"}
    hls, mcd, prithvi = summary["hls"], summary["mcd64a1"], summary["prithvi"]
    standard, shadow = hls["areas_ha"]["fmask_standard"], hls["areas_ha"]["terrain_shadow_included"]
    es = language == "es"
    rows = [
        {"method": "HLS dNBR ≥ 0.27, píxeles despejados en ambas fechas (mínimo)" if es else
         "HLS dNBR ≥ 0.27, pixels clear on both dates (lower bound)", "resolution_m": 30,
         "burned_ha": standard["moderate"]["hotspot_anchored"]},
        {"method": "HLS dNBR ≥ 0.10, píxeles despejados en ambas fechas" if es else
         "HLS dNBR ≥ 0.10, pixels clear on both dates", "resolution_m": 30,
         "burned_ha": standard["low"]["hotspot_anchored"]},
        {"method": "HLS dNBR ≥ 0.10, incluida la sombra del relieve" if es else
         "HLS dNBR ≥ 0.10, terrain shadow included", "resolution_m": 30,
         "burned_ha": shadow["low"]["hotspot_anchored"]},
        {"method": "Área quemada MODIS MCD64A1" if es else "MODIS MCD64A1 burned area", "resolution_m": 500,
         "burned_ha": mcd["burned_ha_jul_aug"]},
        {"method": "Prithvi-EO-2.0 BurnScars, parches que tocan los focos (prueba fuera de dominio)" if es else
         "Prithvi-EO-2.0 BurnScars, patches touching the hotspots (out-of-domain test)",
         "resolution_m": 30, "burned_ha": prithvi["burned_ha_hotspot_anchored"]},
    ]
    return {
        "status": "available",
        "name": summary["case"]["name"],
        "reference": summary["case"]["reference"],
        "event_window": [first, last],
        "scenes": {"pre": hls["pre_scene"]["date"], "post": hls["post_scene"]["date"]},
        "hotspots": summary["firms"]["hotspots_used"],
        "range_ha": [standard["moderate"]["hotspot_anchored"], shadow["low"]["hotspot_anchored"]],
        "rows": rows,
        "figures": list(CASE_FIGURES),
        "caveats": [
            "Los umbrales no se calibraron para este matorral árido: el área casi se duplica entre dNBR 0.27 y 0.10.",
            "La máscara de calidad de HLS marca como agua la sombra invernal de las laderas: las áreas con píxeles "
            "despejados son mínimos.",
            "MCD64A1 cuenta celdas enteras de 21.5 ha; Prithvi se entrenó con incendios de EE. UU. y también marca "
            "laderas no quemadas.",
            "No se validó con un perímetro de campo ni con una cifra oficial de CONAE.",
        ] if es else [
            "Thresholds were not calibrated for this arid shrubland: the area roughly doubles between dNBR 0.27 and 0.10.",
            "Steep winter shadow is masked as water by the HLS quality mask, so clear-pixel areas are lower bounds.",
            "MCD64A1 counts whole 21.5 ha cells; Prithvi was trained on US burn scars and also marks unburned slopes.",
            "Not validated against a field perimeter or an official CONAE figure.",
        ],
        "licences": summary["licences"],
    }


def section_forest_drivers(connection, territory: dict[str, Any], year: int) -> dict[str, Any]:
    """Tree-cover loss with its dominant driver for any country (Global Forest Watch statistics)."""
    path = CONTEXT / "forest_drivers/gfw_drivers.parquet"
    if not path.exists() or territory["type"] != "country":
        return {"status": "not_available",
                "reason": "tree-cover loss by driver is published by country and first-level unit"}
    name = GFW_NAMES.get(territory["country"], territory["country"])
    rows = connection.execute(
        f"""SELECT year, sum(tc_loss_ha), sum(tc_loss_ha) FILTER (WHERE driver='Wildfire')
        FROM read_parquet('{path.as_posix()}') WHERE level='country' AND country=? GROUP BY 1 ORDER BY 1""",
        [name],
    ).fetchall()
    if not rows:
        return {"status": "not_available", "reason": f"no tree-cover loss statistics for {territory['country']}"}
    drivers = connection.execute(
        f"""SELECT driver, sum(tc_loss_ha) FROM read_parquet('{path.as_posix()}')
        WHERE level='country' AND country=? AND year=? GROUP BY 1 ORDER BY 2 DESC""",
        [name, year],
    ).fetchall()
    by_year = [{"year": int(y), "loss_ha": float(t or 0), "loss_ha_with_fire": float(f or 0)} for y, t, f in rows]
    selected = next((r for r in by_year if r["year"] == year), None)
    manifest_path = CONTEXT / "forest_drivers/gfw_drivers.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    return {
        "status": "available",
        "source_kind": "gfw_drivers",
        "definition": "tree-cover loss (Hansen/UMD, canopy >= 30 %) by dominant driver (Global Forest Watch); "
        "'wildfire' = 1 km cells where fire was the dominant driver of loss",
        "caveats": ["Tree-cover loss is not deforestation.",
                    "The driver is the dominant one per 1 km cell (Sims et al. 2025), not a hectare-by-hectare cause.",
                    "The Hansen method changed in 2011-2012: do not read a trend across that break."],
        "validation": "Global Forest Watch country statistics, version 2025 (CC BY 4.0)",
        "source_version": manifest.get("product", "GFW tree-cover loss by driver"),
        "forest_2000_ha": None,
        "by_year": by_year,
        "by_driver": [{"driver": d, "loss_ha": float(v or 0)} for d, v in drivers],
        "selected_year": selected,
        "last_year_available": by_year[-1]["year"],
        "cross_check": None,
    }


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
    if not by_year:
        # Outside Peru: country statistics by dominant driver (Global Forest Watch).
        return section_forest_drivers(connection, territory, year)
    return {
        "status": "available",
        "definition": "tree-cover loss (Hansen/UMD, canopy >= 30 % in 2000); 'with fire' = cell with "
        "satellite fire activity in the same or the previous year",
        "caveats": [
            "Tree-cover loss is not deforestation: it counts stand-replacing disturbance, including "
            "fire-killed forest and plantation harvest.",
            "'With fire' shows co-location, not causation.",
            "Hansen's method changed in 2011–2012 (Landsat 8): do not read a trend across that break.",
        ],
        "validation": "Peru totals 2001–2024 within 0.3–0.6 % of Global Forest Watch (GADM, >30 % canopy)",
        "cross_check": cross_check("forest_peru_geobosques", territory),
        "source_version": (manifest.get("source") or {}).get("version"),
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
    keys = sorted({alias for u in ubigeos if u[:2] in names for alias in CLIMATE_ALIASES.get(
        _key(names[u[:2]]), [_key(names[u[:2]])])})
    if not keys:
        return {"status": "not_available", "reason": "climate is available for Peruvian departments only"}
    # The drought flag is meaningless where the month is climatologically dry (coastal desert,
    # Andean dry season): below DRY_MONTH_MM of normal rainfall it is reported as not applicable.
    # Rainfall comes from CHIRPS (satellite and gauges, 0.05 degree) where available: NASA POWER rainfall
    # anomalies agree with it only moderately in Peru (validation file climate_peru_chirps). Air dryness
    # (vapour-pressure deficit) always comes from NASA POWER.
    chirps_path = CONTEXT / "climate/chirps_department_month.parquet"
    chirps = (f"SELECT department_key, year, month, chirps_mm, chirps_z, chirps_percentile "
              f"FROM read_parquet('{chirps_path.as_posix()}')" if chirps_path.exists() else
              "SELECT NULL::VARCHAR AS department_key, NULL::BIGINT AS year, NULL::BIGINT AS month, "
              "NULL::DOUBLE AS chirps_mm, NULL::DOUBLE AS chirps_z, NULL::DOUBLE AS chirps_percentile WHERE false")
    rows = connection.execute(
        f"""WITH c AS (SELECT * FROM read_parquet('{path.as_posix()}')
                WHERE department_key IN (SELECT unnest(?::VARCHAR[]))),
            h AS ({chirps}),
            normal AS (SELECT department_key, month, avg(precip_mm) AS normal_mm FROM c
                WHERE year BETWEEN 2002 AND 2024 GROUP BY ALL),
            normal_h AS (SELECT department_key, month, avg(chirps_mm) AS normal_h FROM h
                WHERE year BETWEEN 2002 AND 2024 GROUP BY ALL)
        SELECT c.department, c.month, c.precip_mm::DOUBLE, c.precip_z::DOUBLE, c.precip_percentile::DOUBLE,
            c.vpd_kpa::DOUBLE, c.vpd_z::DOUBLE, c.drought, n.normal_mm::DOUBLE,
            h.chirps_mm::DOUBLE, h.chirps_z::DOUBLE, h.chirps_percentile::DOUBLE, nh.normal_h::DOUBLE
        FROM c JOIN normal n USING(department_key, month)
        LEFT JOIN h ON h.department_key = c.department_key AND h.year = c.year AND h.month = c.month
        LEFT JOIN normal_h nh ON nh.department_key = c.department_key AND nh.month = c.month
        WHERE c.year=? ORDER BY c.department, c.month""",
        [keys, year],
    ).fetchall()

    def state(row: tuple) -> dict[str, Any]:
        d, m, p, pz, pp, v, vz, dr, nm, hp, hz, hpp, hn = row
        if hz is not None:
            flag = hz <= -1 and vz is not None and vz >= 1
            precip = {"precip_mm": hp, "precip_z": hz, "precip_percentile": hpp, "normal_precip_mm": hn,
                      "precip_source": "CHIRPS v2.0"}
        else:
            flag = dr
            precip = {"precip_mm": p, "precip_z": pz, "precip_percentile": pp, "normal_precip_mm": nm,
                      "precip_source": "NASA POWER"}
        normal = precip["normal_precip_mm"]
        drought = None if normal is None or normal < DRY_MONTH_MM or flag is None else bool(flag)
        return {"department": d, "month": m, **precip, "power_precip_z": pz, "vpd_kpa": v, "vpd_z": vz,
                "drought": drought}

    states = [state(row) for row in rows]
    selected = [{k: s[k] for k in s if k != "month"} for s in states if s["month"] == month]
    season = {}
    for s in states:
        if s["month"] in SEASON_MONTHS:
            season.setdefault(s["department"], []).append((s["precip_z"], s["vpd_z"], s["drought"]))
    season_summary = [
        {"department": d, "precip_z_mean": statistics.fmean(x[0] for x in v),
         "vpd_z_mean": statistics.fmean(x[1] for x in v), "drought_months": sum(bool(x[2]) for x in v if x[2] is not None)}
        for d, v in season.items()
    ]
    if not selected:
        last = connection.execute(f"SELECT max(year) FROM read_parquet('{path.as_posix()}')").fetchall()[0][0]
        return {"status": "not_available", "reason": f"climate layer covers 2001–{last}"}
    rainfall = "CHIRPS v2.0 (satellite and gauges, 0.05 degree)" if chirps_path.exists() else "NASA POWER v2.10"
    return {
        "status": "available",
        "source": f"Rainfall: {rainfall}; air dryness: NASA POWER v2.10 (MERRA-2, ~0.5 degree); monthly anomalies vs "
        "2002–2024 climatology",
        "note": "Context only: no causal attribution of fire activity. Drought = rainfall z <= -1 and "
        "vapour-pressure deficit z >= +1; not applicable in months with under "
        f"{DRY_MONTH_MM:.0f} mm of normal rainfall.",
        "selected_month": selected,
        "season_jul_oct": season_summary,
        "cross_check": cross_check("climate_peru_chirps", territory),
    }


def _key(text: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
JPEG_MAGIC = bytes([0xFF, 0xD8])
SNPP_FIRST, SNPP_LAST = date(2012, 1, 20), date(2026, 11, 2)
VIIRS_TRUE_COLOUR_FIRST = date(2015, 11, 24)  # first day of VIIRS corrected reflectance in GIBS


NOAA20_IMAGERY = ["VIIRS_NOAA20_CorrectedReflectance_TrueColor", "VIIRS_NOAA20_Thermal_Anomalies_375m_All"]
SNPP_IMAGERY = ["VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS_SNPP_Thermal_Anomalies_375m_All"]
MODIS_IMAGERY = ["MODIS_Terra_CorrectedReflectance_TrueColor", "MODIS_Combined_Thermal_Anomalies_All"]
NOAA20_IMAGERY_FIRST = date(2018, 1, 5)
MIN_IMAGE_BYTES = 15_000  # smaller JPEGs from GIBS are blank tiles (no granule that day)


def gibs_layer_sets(day: date) -> list[list[str]]:
    """Candidate layer sets for a day, best first: a sensor may lack imagery on a given day
    (S-NPP had gaps in mid-2024 and ended on 2 Nov 2026), so the next one is tried."""
    sets = []
    if day >= NOAA20_IMAGERY_FIRST:
        sets.append(NOAA20_IMAGERY)
    if VIIRS_TRUE_COLOUR_FIRST <= day <= SNPP_LAST:
        sets.append(SNPP_IMAGERY)
    sets.append(MODIS_IMAGERY)
    return sets


def gibs_layers(day: date) -> list[str]:
    return gibs_layer_sets(day)[0]


def territory_shape(territory: dict[str, Any]) -> Any:
    if territory["polygon"] is not None:
        return territory["polygon"]
    path = countries_path()
    shapes = dict(country_shapes(str(path), path.stat().st_mtime_ns))
    return shapes.get(territory["country"])


def section_imagery(connection, territory: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    """Real NASA GIBS imagery of the most active day of the month and 60 days earlier."""
    outline_shape = territory_shape(territory)
    if outline_shape is None or outline_shape.is_empty:
        return {"status": "not_available", "reason": "no outline for this territory"}
    peak = connection.execute(
        """SELECT day, sum(active_harmonized) FROM selected_activity WHERE year(day)=? AND month(day)=?
        GROUP BY 1 ORDER BY 2 DESC NULLS LAST, 1 LIMIT 1""",
        [year, month],
    ).fetchone()
    after = peak[0] if peak else date(year, month, 15)
    after = after if isinstance(after, date) else date.fromisoformat(str(after)[:10])
    before = after - timedelta(days=60)
    west, south, east, north = outline_shape.bounds
    pad_x, pad_y = (east - west) * 0.06 + 0.05, (north - south) * 0.06 + 0.05
    bbox = [west - pad_x, south - pad_y, east + pad_x, north + pad_y]
    simple = outline_shape.simplify(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 250, preserve_topology=True)
    parts = list(simple.geoms) if hasattr(simple, "geoms") else [simple]
    parts = sorted((g for g in parts if g.geom_type == "Polygon"), key=lambda g: -g.area)[:12]
    return {
        "status": "available",
        "source": "NASA GIBS (Worldview) corrected reflectance with thermal anomalies; real imagery, may "
        "show clouds or smoke",
        "bbox": [round(v, 4) for v in bbox],
        "outline": [[[round(x, 4), round(y, 4)] for x, y in g.exterior.coords] for g in parts],
        "after": {"date": after.isoformat(), "layers": gibs_layers(after), "candidates": gibs_layer_sets(after),
                  "peak_activity": peak[1] if peak else None},
        "before": {"date": before.isoformat(), "layers": gibs_layers(before), "candidates": gibs_layer_sets(before)},
    }


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
        "events_registry": "{year}: {events} significant fire events detected by satellite; {label}: {emergencies}.",
        "indeci_partial": " (INDECI records available through {through}.)",
        "forest": "Tree-cover loss {year}: {loss} ha, of which {fire} ha in cells with fire activity.",
        "forest_gfw": "Tree-cover loss {year} (Global Forest Watch): {loss} ha, of which {fire} ha where wildfire was the dominant driver.",
        "burned": "Burned area {year} (MODIS MCD64A1, GWIS): {area} ha.",
        "burn_case": "Burned area mapped at 30 m (Landsat, case study): about {low}–{high} ha depending on threshold and terrain shadow; MODIS MCD64A1 gives {mcd} ha.",
        "burned_month": "Burned area in {month} {year} (MODIS MCD64A1, GWIS): {area} ha, rank {rank} of {of} for that month.",
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
        "events_registry": "{year}: {events} evento(s) de incendio significativo(s) detectado(s) por satélite; {label}: {emergencies}.",
        "indeci_partial": " (registros de INDECI disponibles hasta {through}).",
        "forest": "Pérdida de cobertura arbórea {year}: {loss} ha, de las cuales {fire} ha en celdas con actividad de fuego.",
        "forest_gfw": "Pérdida de cobertura arbórea {year} (Global Forest Watch): {loss} ha, de las cuales {fire} ha donde el incendio fue la causa dominante.",
        "burned": "Área quemada {year} (MODIS MCD64A1, GWIS): {area} ha.",
        "burn_case": "Área quemada cartografiada a 30 m (Landsat, caso de estudio): entre unas {low} y {high} ha según el umbral y la sombra del relieve; MODIS MCD64A1 da {mcd} ha.",
        "burned_month": "Área quemada en {month} de {year} (MODIS MCD64A1, GWIS): {area} ha, puesto {rank} de {of} para ese mes.",
        "climate": "Clima {period}: {drought} de {total} departamento(s) en condición de sequía (baja precipitación y alto déficit de presión de vapor).",
    },
}


MONTH_NAMES = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre",
           "noviembre", "diciembre"],
}
HEADLINE = {
    "en": {
        "record": "{month} {year} was the highest {month} in {n} years: {anomaly} % above the median.",
        "above": "{month} {year} was above the normal range: {anomaly} % against the median (rank {rank} of {n}).",
        "below": "{month} {year} was below the normal range: {anomaly} % against the median (rank {rank} of {n}).",
        "normal": "{month} {year} was within the normal range ({anomaly} % against the median).",
        "mtd": "{month} {year} so far: {value} against {median} for the same days of other years.",
        "none": "{month} {year} has no comparable value yet.",
    },
    "es": {
        "record": "{month} de {year} fue el {month} más alto en {n} años: {anomaly} % sobre la mediana.",
        "above": "{month} de {year} estuvo por encima del rango normal: {anomaly} % respecto de la mediana "
        "(puesto {rank} de {n}).",
        "below": "{month} de {year} estuvo por debajo del rango normal: {anomaly} % respecto de la mediana "
        "(puesto {rank} de {n}).",
        "normal": "{month} de {year} estuvo dentro del rango normal ({anomaly} % respecto de la mediana).",
        "mtd": "{month} de {year} hasta ahora: {value} frente a {median} en los mismos días de otros años.",
        "none": "{month} de {year} aún no tiene un valor comparable.",
    },
}


def headline(report: dict[str, Any]) -> dict[str, Any]:
    """One-sentence verdict; 'normal' means inside the p10–p90 band of the other years."""
    language = report["language"]
    month = report["sections"]["current"]["month"]
    name = MONTH_NAMES[language][report["period"]["month"] - 1]
    words = HEADLINE[language]
    base = {"month": name, "year": report["period"]["year"]}
    if month["value"] is not None and month["anomaly_percent"] is not None:
        anomaly = format_number(month["anomaly_percent"], language, 0, sign=True)
        values = {**base, "anomaly": anomaly, "rank": month["rank"], "n": month["rank_of"]}
        if month["rank"] == 1:
            kind = "record"
        elif month["historical_p90"] is not None and month["value"] > month["historical_p90"]:
            kind = "above"
        elif month["historical_p10"] is not None and month["value"] < month["historical_p10"]:
            kind = "below"
        else:
            kind = "normal"
        text = words[kind].format(**values)
        return {"kind": kind, "text": text[0].upper() + text[1:]}
    current = report["sections"]["current"]["month_to_date"]
    if current and current["value"] is not None and current["historical_median"] is not None:
        text = words["mtd"].format(**base, value=format_number(current["value"], language),
                                   median=format_number(current["historical_median"], language))
        return {"kind": "in_progress", "text": text[0].upper() + text[1:]}
    text = words["none"].format(**base)
    return {"kind": "not_available", "text": text[0].upper() + text[1:]}


def summary(report: dict[str, Any]) -> list[str]:
    return [text for _, text in summary_items(report)]


def summary_items(report: dict[str, Any]) -> list[tuple[str, str]]:
    """(topic, sentence) pairs: current, mtd, season, trend, events, forest, climate."""
    language = report["language"]
    t = TEXT[language]

    def n(value: Any, digits: int = 0, sign: bool = False) -> str:
        return format_number(value, language, digits, sign)

    s = report["sections"]
    period = f"{report['period']['year']}-{report['period']['month']:02d}"
    lines = []
    month = s["current"]["month"]
    if month["value"] is not None and month["anomaly_percent"] is not None:
        lines.append(("current", t["current"].format(period=period, value=n(month["value"]), anomaly=n(month["anomaly_percent"], sign=True),
                                         n=month["historical_n"], rank=month["rank"], rank_of=month["rank_of"])))
    else:
        lines.append(("current", t["current_none"].format(period=period, status=month["status"])))
    mtd = s["current"]["month_to_date"]
    if mtd and mtd["value"] is not None and mtd["historical_median"] is not None:
        lines.append(("mtd", t["mtd"].format(days=mtd["valid_days"], through=mtd["through_day"], value=n(mtd["value"]),
                                     median=n(mtd["historical_median"]))))
    season = s["history"].get("season_jul_oct") or {}
    if season.get("anomaly_percent") is not None:
        lines.append(("season", t["season"].format(year=report["period"]["year"], rank=season["rank"],
                                        rank_of=season["rank_of"], anomaly=n(season["anomaly_percent"], sign=True))))
    h = s["history"]
    if h.get("trend_period"):
        words = t["trend_words"]
        lines.append(("trend", t["trend"].format(
            start=h["trend_period"][0], end=h["trend_period"][1],
            harm=words[h["trend_harmonized"]["direction"]].format(slope=n(h["trend_harmonized"]["slope_pct_per_year"] or 0, 1, True)),
            raw=words[h["trend_raw_pixels"]["direction"]].format(slope=n(h["trend_raw_pixels"]["slope_pct_per_year"] or 0, 1, True)),
        )))
    ev = s["events"]
    if ev["status"] == "available" and ev.get("selected_year"):
        row = ev["selected_year"]
        if row["emergencies"] is not None:
            label = ev.get("emergencies_label")
            if label and "INDECI" not in label:
                line = t["events_registry"].format(year=row["year"], events=n(row["significant_events"]),
                                                   emergencies=n(row["emergencies"]), label=label)
            else:
                line = t["events"].format(year=row["year"], events=n(row["significant_events"]), emergencies=n(row["emergencies"]))
            through = (ev.get("emergencies_coverage") or [None, None])[1]
            if through and int(through[:4]) == row["year"] and through[5:] != "12-31":
                line += t["indeci_partial"].format(through=through)
            lines.append(("events", line))
        else:
            lines.append(("events", t["events_only"].format(year=row["year"], events=n(row["significant_events"]))))
    bc = s.get("burn_case") or {}
    if bc.get("status") == "available":
        mcd = next(r["burned_ha"] for r in bc["rows"] if r["resolution_m"] == 500)
        lines.append(("burned", t["burn_case"].format(low=n(round(bc["range_ha"][0], -2)), high=n(round(bc["range_ha"][1], -2)),
                                                      mcd=n(round(mcd, -2)))))
    ba = s.get("burned_area") or {}
    if ba.get("status") == "available":
        if ba.get("selected_month"):
            sm = ba["selected_month"]
            lines.append(("burned", t["burned_month"].format(
                month=MONTH_NAMES[language][sm["month"] - 1], year=sm["year"], area=n(sm["burned_ha"]),
                rank=sm["rank"], of=sm["rank_of"])))
        elif ba.get("selected_year"):
            lines.append(("burned", t["burned"].format(year=ba["selected_year"]["year"],
                                                       area=n(ba["selected_year"]["burned_ha"]))))
    fo = s["forest"]
    if fo["status"] == "available" and fo.get("selected_year"):
        lines.append(("forest", t["forest_gfw" if fo.get("source_kind") == "gfw_drivers" else "forest"].format(
                                        year=fo["selected_year"]["year"], loss=n(fo["selected_year"]["loss_ha"]),
                                        fire=n(fo["selected_year"]["loss_ha_with_fire"]))))
    cl = s["climate"]
    if cl["status"] == "available":
        applicable = [r for r in cl["selected_month"] if r["drought"] is not None]
        if applicable:
            lines.append(("climate", t["climate"].format(period=period, drought=sum(r["drought"] for r in applicable),
                                             total=len(applicable))))
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
            "current": section_current(months, selected, current, request.year),
            "history": section_history(connection, months, request.year),
            "events": section_events(connection, territory, request.year, request.language),
            "forest": section_forest(connection, territory, request.year),
            "burned_area": section_burned_area(connection, territory, request.year, request.month),
            "burn_case": section_burn_case(territory, request.year, request.month, request.language),
            "climate": section_climate(territory, request.year, request.month, connection),
            "quality": section_quality(selected, manifest),
            "imagery": section_imagery(connection, territory, request.year, request.month),
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
    report["headline"] = headline(report)
    report["summary_items"] = [{"topic": k, "text": v} for k, v in summary_items(report)]
    report["summary"] = [item["text"] for item in report["summary_items"]]
    report["summary_mode"] = "template"
    cache = DATA / "jobs/reports"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{identifier}.json").write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    return report


class PriorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=2002, le=2100)
    month: int = Field(ge=1, le=12)
    language: Literal["en", "es"] = "en"


def priority_row(code: str, name: str, report: dict[str, Any]) -> dict[str, Any]:
    s = report["sections"]
    month, season = s["current"]["month"], s["history"].get("season_jul_oct") or {}
    events = (s["events"].get("selected_year") or {}) if s["events"]["status"] == "available" else {}
    forest = (s["forest"].get("selected_year") or {}) if s["forest"]["status"] == "available" else {}
    climate = (s["climate"].get("selected_month") or []) if s["climate"]["status"] == "available" else []
    flags = [c["drought"] for c in climate if c["drought"] is not None]
    return {
        "code": code,
        "name": name,
        "report_id": report["id"],
        "month_value": month["value"],
        "month_anomaly": month["anomaly_percent"],
        "month_rank": month["rank"],
        "month_rank_of": month["rank_of"],
        "month_status": month["status"],
        "season_rank": season.get("rank"),
        "season_rank_of": season.get("rank_of"),
        "season_anomaly": season.get("anomaly_percent"),
        "trend_harmonized": s["history"]["trend_harmonized"]["slope_pct_per_year"],
        "trend_harmonized_direction": s["history"]["trend_harmonized"]["direction"],
        "trend_raw": s["history"]["trend_raw_pixels"]["slope_pct_per_year"],
        "significant_events": events.get("significant_events"),
        "emergencies": events.get("emergencies"),
        "forest_loss_ha": forest.get("loss_ha"),
        "forest_loss_with_fire_ha": forest.get("loss_ha_with_fire"),
        "drought": (any(flags) if flags else None),
    }


@router.post("/api/reports/priority")
def priority(request: PriorityRequest) -> dict[str, Any]:
    """Peruvian departments side by side, each indicator in its own column (no composite score)."""
    from concurrent.futures import ThreadPoolExecutor

    manifest, _ = published()
    departments = sorted({(p["ubigeo"][:2], p["department"]) for p, _ in districts()})
    if not departments:
        raise HTTPException(409, "The district layer is not built")
    cache = DATA / "jobs/priority" / f"{manifest['id']}-{request.year}-{request.month:02d}-{request.language}.json"
    if cache.exists():
        return load_json(cache)

    def one(item: tuple[str, str]) -> dict[str, Any]:
        code, name = item
        report = build_report(ReportRequest(ubigeo=code, year=request.year, month=request.month,
                                            language=request.language))
        return priority_row(code, display_name(name), report)

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, departments))
    result = {
        "dataset_id": manifest["id"],
        "year": request.year,
        "month": request.month,
        "level": "department",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": rows,
        "note": "Each indicator is reported separately and can be sorted; NINA does not combine them into "
        "a single score. Significant events: at least 5 active cell-days (VIIRS era). Emergencies: INDECI records.",
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    return result


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


@router.get("/api/reports/territorial/{identifier}/case-figure/{name}")
def report_case_figure(identifier: str, name: str) -> FileResponse:
    """A figure of the 30 m burned-area case study shown in this report."""
    report = stored(identifier)
    case = report["sections"].get("burn_case") or {}
    if case.get("status") != "available" or name not in CASE_FIGURES:
        raise HTTPException(404, "No such figure for this report")
    path = CONTEXT / "burn_case" / name
    if not path.exists():
        raise HTTPException(404, "Figure not built")
    return FileResponse(path, media_type="image/png")


@router.get("/api/reports/territorial/{identifier}/imagery/{which}")
def report_imagery(identifier: str, which: Literal["before", "after"]) -> FileResponse:
    """GIBS image for the report (cached); 503 when NASA GIBS cannot be reached."""
    from .remote import nasa_client

    report = stored(identifier)
    imagery = report["sections"].get("imagery") or {}
    if imagery.get("status") != "available":
        raise HTTPException(404, "No imagery for this report")
    west, south, east, north = imagery["bbox"]
    width = 640
    height = max(200, min(900, round(width * (north - south) / max(east - west, 1e-6))))
    shot = imagery[which]
    folder = DATA / "tiles/reports"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([imagery["bbox"], shot["date"], width]).encode()).hexdigest()[:20]
    path = folder / f"{key}.jpg"
    if not path.exists():
        content = None
        try:
            with nasa_client(60) as client:
                for layers in shot.get("candidates") or [shot["layers"]]:
                    params = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1", "LAYERS": ",".join(layers),
                              "STYLES": "", "FORMAT": "image/jpeg", "WIDTH": width, "HEIGHT": height,
                              "SRS": "EPSG:4326", "BBOX": f"{west},{south},{east},{north}", "TIME": shot["date"]}
                    response = client.get(GIBS_WMS, params=params)
                    body = response.content
                    if (response.status_code == 200 and body.startswith(JPEG_MAGIC)
                            and MIN_IMAGE_BYTES <= len(body) <= 6_000_000):
                        content = body
                        break
        except Exception:
            raise HTTPException(503, "NASA GIBS imagery temporarily unavailable") from None
        if content is None:
            raise HTTPException(503, "NASA GIBS has no imagery for that day")
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    return FileResponse(path, media_type="image/jpeg")


README = {
    "en": """NINA · Territorial fire evidence report
=======================================

Territory: {territory} ({type})
Period: {period}
Dataset: {dataset} (method {method}, {status})
Generated: {generated}
Request: {request}

Files
- report.pdf: the report, ready to print or share.
- report.html: the same report, self-contained (open it in a browser).
- report.json: every figure of the report, with its section and status.
- monthly_activity.csv: harmonized monthly activity, anomaly and status (null = no comparable value, never zero).
- annual_series.csv: annual harmonized activity and raw pixel counts (raw counts mix sensors; compare only the harmonized series across 2012).
- events_by_year.csv: detected fire events (VIIRS era) and registered emergencies or incidents.
- forest_loss_by_year.csv: Hansen/UMD tree-cover loss, total and in cells with fire activity.
- climate_month.csv: NASA POWER precipitation and air dryness for the month (context only).

Unit: VIIRS S-NPP-equivalent active cell-days (H3 resolution 7, about 5 km2). It measures detected activity,
not the number of fires, burned area or damage. The harmonized product is {status}.

Citation and disclaimer (NASA FIRMS)
{legal}

References
{references}
""",
    "es": """NINA · Informe técnico territorial de actividad de fuego
=========================================================

Territorio: {territory} ({type})
Período: {period}
Conjunto de datos: {dataset} (método {method}, {status})
Generado: {generated}
Solicitud: {request}

Archivos
- report.pdf: el informe, listo para imprimir o compartir.
- report.html: el mismo informe, autocontenido (ábrelo en un navegador).
- report.json: todas las cifras del informe, con su sección y estado.
- monthly_activity.csv: actividad mensual armonizada, anomalía y estado (null = sin valor comparable, nunca cero).
- annual_series.csv: actividad anual armonizada y conteo crudo de píxeles (el conteo crudo mezcla sensores; a través de 2012 compara solo la serie armonizada).
- events_by_year.csv: incendios detectados (era VIIRS) y emergencias o incidentes registrados.
- forest_loss_by_year.csv: pérdida de cobertura arbórea Hansen/UMD, total y en celdas con actividad de fuego.
- climate_month.csv: precipitación y sequedad del aire de NASA POWER en el mes (solo contexto).

Unidad: celdas-día activas equivalentes a VIIRS S-NPP (H3 resolución 7, unos 5 km2). Mide actividad detectada, no
número de incendios, área quemada ni daños. El producto armonizado es {status}.

Cita y aviso (NASA FIRMS)
{legal}

Referencias
{references}
""",
}


def csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    """UTF-8 with BOM (opens correctly in Excel); empty cells for missing values."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def report_images(identifier: str, report: dict[str, Any]) -> dict[str, Path]:
    """Local paths of the cached GIBS images of a report (fetched once) and of its case-study figure; missing ones
    are skipped."""
    paths: dict[str, Path] = {}
    case = report["sections"].get("burn_case") or {}
    if case.get("status") == "available" and (CONTEXT / "burn_case" / case["figures"][0]).exists():
        paths["case"] = CONTEXT / "burn_case" / case["figures"][0]
    if (report["sections"].get("imagery") or {}).get("status") == "available":
        for which in ("before", "after"):
            try:
                paths[which] = Path(report_imagery(identifier, which).path)
            except HTTPException:
                continue
    return paths


def report_filename(report: dict[str, Any], extension: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in report["territory"]["name"]).strip("-")[:40] or "territory"
    return f"NINA_report_{slug}_{report['period']['year']}-{report['period']['month']:02d}.{extension}"


def report_pdf_bytes(identifier: str, report: dict[str, Any]) -> bytes:
    """The PDF of a report, cached next to it (a report never changes once stored)."""
    from .report_pdf import build_pdf

    path = DATA / "jobs/reports" / f"{identifier}.pdf"
    if path.exists():
        return path.read_bytes()
    content = build_pdf(report, report_images(identifier, report))
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return content


@router.get("/api/reports/territorial/{identifier}/pdf")
def report_pdf(identifier: str):
    """The report as an A4 PDF, downloaded directly (no print dialog)."""
    from fastapi.responses import Response

    report = stored(identifier)
    return Response(report_pdf_bytes(identifier, report), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{report_filename(report, "pdf")}"'})


@router.get("/api/reports/territorial/{identifier}/package")
def report_package(identifier: str):
    """ZIP with the self-contained report, its figures as JSON and CSV, and a README with the FIRMS citation."""
    import base64
    import io
    import zipfile

    from fastapi.responses import Response

    from .report_document import LABELS, render

    report = stored(identifier)
    images: dict[str, str] = {}
    case = report["sections"].get("burn_case") or {}
    if case.get("status") == "available" and (CONTEXT / "burn_case" / case["figures"][0]).exists():
        images["case"] = "data:image/png;base64," + base64.b64encode(
            (CONTEXT / "burn_case" / case["figures"][0]).read_bytes()).decode()
    if (report["sections"].get("imagery") or {}).get("status") == "available":
        for which in ("before", "after"):
            try:
                served = report_imagery(identifier, which)
                images[which] = "data:image/jpeg;base64," + base64.b64encode(open(served.path, "rb").read()).decode()
            except HTTPException:
                continue
    s = report["sections"]
    language = report["language"] if report["language"] in README else "en"
    month_name = LABELS[language]["months_long"][report["period"]["month"] - 1]
    status = ("validated" if report["validation_status"] == "validated" else "experimental") if language == "en" else (
        "validado" if report["validation_status"] == "validated" else "experimental")
    readme = README[language].format(
        territory=report["territory"]["name"], type=report["territory"]["type"],
        period=f"{month_name} {report['period']['year']}", dataset=report["dataset_id"],
        method=report["method_version"], status=status, generated=report["generated_at"],
        request=json.dumps({k: v for k, v in report["request"].items() if k != "geometry"}, ensure_ascii=False),
        legal=report["legal"], references="\n".join(report["references"]))
    files = {
        "README.txt": readme.encode("utf-8"),
        "report.pdf": report_pdf_bytes(identifier, report),
        "report.html": render(report, embedded_images=images).encode("utf-8"),
        "report.json": json.dumps(report, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
        "monthly_activity.csv": csv_bytes(s["current"].get("calendar") or [],
                                          ["year", "month", "value", "status", "anomaly_percent"]),
        "annual_series.csv": csv_bytes(s["history"].get("annual") or [], ["year", "harmonized", "raw_pixels"]),
    }
    if s["events"]["status"] == "available":
        files["events_by_year.csv"] = csv_bytes(s["events"]["by_year"], ["year", "events", "significant_events", "emergencies"])
    if (s.get("burned_area") or {}).get("status") == "available":
        files["burned_area_by_year.csv"] = csv_bytes(s["burned_area"]["by_year"], ["year", "burned_ha"])
    if s["forest"]["status"] == "available":
        files["forest_loss_by_year.csv"] = csv_bytes(s["forest"]["by_year"], ["year", "loss_ha", "loss_ha_with_fire"])
    if s["climate"]["status"] == "available":
        files["climate_month.csv"] = csv_bytes(s["climate"]["selected_month"],
                                               ["department", "precip_mm", "normal_precip_mm", "precip_percentile",
                                                "precip_z", "vpd_kpa", "vpd_z", "drought"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    filename = report_filename(report, "zip")
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/reports/territorial/{identifier}/document", response_class=HTMLResponse)
def report_document(identifier: str) -> HTMLResponse:
    from .report_document import render

    return HTMLResponse(render(stored(identifier)))
