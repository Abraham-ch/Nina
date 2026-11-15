"""Queries over the published harmonized product. The API never calibrates sensors."""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import os
import re
import statistics
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
import shapely
import shapely.affinity
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.background import BackgroundTask

from .config import DATA, ROOT, SOURCE

ARTIFACTS = SOURCE / "harmonized"
REVIEW_ARTIFACTS = SOURCE / "review"
REPORTS = SOURCE / "interim/harmonization"
router = APIRouter(tags=["Harmonized activity"])
UNIT = "equivalent_VIIRS_active_cell_days"
ANALYSIS_VERSION = "2"
MAX_GEOMETRY_BYTES = 100000
MAX_LONGITUDE = 180
MAX_LATITUDE = 90
# Terra-only months (before Aqua, July 2002) are not served (ADR 0005).
CLIMATOLOGY_FIRST_YEAR = 2002
MAX_BAD_DAY_FRACTION = 0.20
MIN_HISTORY_YEARS = 5
MAX_MAP_POINTS = 10000
# A month keeps its value when at most this share of its observed cell-days lacks a validated
# coefficient; the share is reported and the value is the validated sum (ADR 0005).
MAX_UNVALIDATED_SHARE = 0.01
# With a free polygon, countries holding less than this share of the selected cells are border
# slivers of the generalized 1:110m outlines and are left out (reported in the response).
BORDER_SLIVER_SHARE = 0.02
# Shorter windows have strong sampling bias (MODIS guide); no anomaly below 8 days.
MIN_AGGREGATION_DAYS = 8


class HarmonizedSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(default="world", max_length=100)
    year_start: int = Field(default=2001, ge=2000, le=2100)
    year_end: int = Field(default=2026, ge=2000, le=2100)
    selected_year: int = Field(default=2026, ge=2000, le=2100)
    selected_month: int = Field(default=7, ge=1, le=12)
    geometry: dict | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        if not self.year_start <= self.selected_year <= self.year_end:
            raise ValueError("The selected year must be inside the year range")
        if self.geometry is not None:
            try:
                shape = shapely.geometry.shape(self.geometry)
                west, south, east, north = shape.bounds
                valid = shape.geom_type in {"Polygon", "MultiPolygon"} and shape.is_valid
                valid = (
                    valid
                    and not shape.is_empty
                    and len(json.dumps(self.geometry)) <= MAX_GEOMETRY_BYTES
                )
                valid = valid and -MAX_LONGITUDE <= west < east <= MAX_LONGITUDE
                valid = valid and -MAX_LATITUDE <= south < north <= MAX_LATITUDE
                if not valid:
                    raise ValueError()
            except Exception as error:
                raise ValueError("Invalid WGS84 polygon") from error
        return self


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    available: bool
    status: str
    id: str | None = None
    method_version: str | None = None
    gates: dict[str, bool] = Field(default_factory=dict)


class CalendarMonth(BaseModel):
    year: int
    month: int
    value: float | None
    observed_activity: float | None
    unit: str
    status: Literal[
        "not_available",
        "unvalidated_domain",
        "incomplete_coverage",
        "partial_archive",
        "provisional",
        "complete",
    ]
    data_gap: bool
    partial_coverage: bool
    is_provisional: bool
    expected_region_days: int
    valid_region_days: int
    calendar_days: int
    unvalidated_cell_days: int
    unvalidated_share: float = 0.0
    noaa20_filled_days: int = 0
    eligible_for_climatology: bool
    historical_median: float | None
    historical_n: int
    historical_p10: float | None = None
    historical_p90: float | None = None
    anomaly_percent: float | None
    rank: int | None = Field(default=None, description="1 = highest of the compared years")
    rank_of: int = 0


class MonthToDate(BaseModel):
    """The month in progress compared with the same days of the other eligible years."""

    year: int
    month: int
    through_day: int
    valid_days: int = Field(description="Days of the window with valid support; others are skipped")
    value: float | None
    historical_median: float | None
    historical_n: int
    anomaly_percent: float | None
    rank: int | None = None
    rank_of: int = 0
    sampling_bias_warning: bool
    unvalidated_share: float = 0.0


class HarmonizedAnalysis(BaseModel):
    id: str
    selection: HarmonizedSelection
    dataset_id: str
    analysis_version: str
    unit: str
    months: list[CalendarMonth]
    selected: CalendarMonth
    month_to_date: MonthToDate | None = None
    excluded_border_countries: list[str] = Field(default_factory=list)
    harmonized: Literal[True]
    synthetic: Literal[False]
    grid_resolution: int
    local_cloud_opportunities: str
    method_version: str
    references: list[str]
    legal: str
    limitations: list[str]
    provenance: dict[str, Any]
    scientifically_validated: bool
    validation_status: Literal["validated", "experimental"]


class PointsResponse(BaseModel):
    analysis_id: str
    dataset_id: str
    validation_status: Literal["validated", "experimental"]
    references: list[str]
    type: Literal["FeatureCollection"]
    representation: Literal["H3_cell_centers"]
    unit: str
    total: int
    shown: int
    sampled: bool
    synthetic: Literal[False]
    features: list[dict[str, Any]]


class AssistantResponse(BaseModel):
    answer: str
    analysis_id: str
    dataset_id: str
    facts: CalendarMonth
    references: list[str]
    mode: Literal["deterministic_grounded"]
    external_llm_used: Literal[False]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/harmonization", response_model=ReadinessResponse)
def readiness():
    pointer = ARTIFACTS / "current.json"
    if pointer.exists():
        manifest = load_json(pointer)
        return {**manifest, "available": manifest.get("status") == "published"}
    review = REVIEW_ARTIFACTS / "current.json"
    if review.exists():
        manifest = load_json(review)
        return {
            **manifest,
            "available": experimental_enabled(),
            "activation_required": not experimental_enabled(),
        }
    status = REPORTS / "status.json"
    if status.exists():
        return {**load_json(status), "available": False}
    prepared = REPORTS / "prepared.json"
    if prepared.exists():
        candidate = load_json(prepared)
        return {
            "available": False,
            "status": "candidate_under_validation",
            "method_version": candidate["method_version"],
            "gates": {"static_mask": candidate["mask_validation"]["passed"]},
            "mask_validation": candidate["mask_validation"],
        }
    return {"available": False, "status": "preparing", "unit": UNIT}


def experimental_enabled():
    return os.getenv("NINA_EXPERIMENTAL_HARMONIZATION", "false").lower() == "true"


def published():
    pointer = ARTIFACTS / "current.json"
    artifact_root = ARTIFACTS
    is_review = False
    if not pointer.exists() and experimental_enabled():
        pointer = REVIEW_ARTIFACTS / "current.json"
        artifact_root = REVIEW_ARTIFACTS
        is_review = True
    if not pointer.exists():
        raise HTTPException(
            409,
            {
                "message": "The harmonized series has not passed validation yet.",
                "readiness": readiness(),
            },
        )
    manifest = load_json(pointer)
    identifier = manifest.get("id", "")
    if (
        not re.fullmatch(r"[a-f0-9]{24}", identifier)
        or manifest.get("status") != ("experimental_candidate" if is_review else "published")
        or not manifest.get("gates")
        or (not is_review and not all(manifest["gates"].values()))
    ):
        raise HTTPException(409, "There is no approved product")
    folder = artifact_root / identifier
    if not all(
        (folder / name).is_file()
        for name in [
            "harmonized_cell_day.parquet",
            "support.parquet",
            "grid_cells.parquet",
            "manifest.json",
        ]
    ):
        raise HTTPException(503, "The published product is incomplete")
    if load_json(folder / "manifest.json") != manifest:
        raise HTTPException(503, "The product manifest does not match its publication")
    try:
        signature = tuple(
            (
                str(folder / name),
                manifest["hashes"][name],
                (folder / name).stat().st_mtime_ns,
                (folder / name).stat().st_size,
            )
            for name in ["harmonized_cell_day.parquet", "support.parquet", "grid_cells.parquet"]
        )
        verify_files(signature)
    except (KeyError, ValueError, OSError):
        raise HTTPException(503, "The product failed its integrity check") from None
    return manifest, folder


@lru_cache(maxsize=4)
def verify_files(signature):
    for name, expected, _, _ in signature:
        digest = hashlib.sha256()
        with Path(name).open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("Invalid hash")


def split_antimeridian(geometry):
    """Cut parts wider than 180° at ±180° instead of letting them cover a band around the globe.

    Natural Earth 1:110m encodes Chukotka (Russia) and Fiji as rings that jump from +180 to
    −180; read naively they cover every longitude. Same rule as the pipeline (ADR 0005).
    """
    parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    fixed = []
    for part in parts:
        west, south, east, north = part.bounds
        if east - west <= 180 or south <= -89.9 or north >= 89.9:
            fixed.append(part)
            continue
        shifted = shapely.make_valid(
            shapely.transform(part, lambda xy: np.where(xy[:, :1] < 0, xy + [360.0, 0.0], xy))
        )
        inside = shifted.intersection(shapely.box(-180, -90, 180, 90))
        beyond = shifted.intersection(shapely.box(180, -90, 540, 90))
        fixed.append(shapely.union(inside, shapely.affinity.translate(beyond, xoff=-360)))
    return shapely.union_all(fixed)


@lru_cache(maxsize=2)
def country_shapes(path: str, modified: int):
    features = load_json(Path(path))["features"]
    return [
        (f["properties"]["name"], split_antimeridian(shapely.geometry.shape(f["geometry"])))
        for f in features
    ]


def selected_countries(selection):
    path = ROOT / "web/public/assets/countries.geojson"
    shapes = country_shapes(str(path), path.stat().st_mtime_ns)
    if selection.country != "world":
        shapes = [(name, shape) for name, shape in shapes if name == selection.country]
        if not shapes:
            raise HTTPException(422, "Unknown country; use the names from /api/places")
    if selection.geometry:
        geometry = shapely.geometry.shape(selection.geometry)
        shapes = [(name, shape) for name, shape in shapes if geometry.intersects(shape)]
    names = [name for name, _ in shapes]
    if selection.country == "world" and not selection.geometry:
        names.append("unassigned")
    return names


@contextmanager
def selection_database(selection, folder):
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit='1GB'")
        connection.execute("SET threads=2")
        scratch = DATA / "query-cache"
        scratch.mkdir(parents=True, exist_ok=True)
        connection.execute("SET temp_directory='" + str(scratch).replace("'", "''") + "'")
        for table in ["harmonized_cell_day", "support", "grid_cells"]:
            path = str(folder / f"{table}.parquet").replace("'", "''")
            connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path}')")
        names = selected_countries(selection)
        connection.execute("CREATE TEMP TABLE selected_countries(country VARCHAR)")
        if names:
            connection.executemany(
                "INSERT INTO selected_countries VALUES (?)", [(n,) for n in names]
            )
        connection.execute("""CREATE TEMP TABLE selected_cells AS SELECT g.* FROM grid_cells g
            WHERE country IN (SELECT country FROM selected_countries)""")
        if selection.geometry:
            geometry = shapely.geometry.shape(selection.geometry)
            shapely.prepare(geometry)
            connection.create_function(
                "inside_selection",
                lambda lat, lon: bool(shapely.covers(geometry, shapely.geometry.Point(lon, lat))),
                [float, float],
                bool,
            )
            west, south, east, north = geometry.bounds
            connection.execute(
                """DELETE FROM selected_cells WHERE NOT (
                longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?)
                OR NOT inside_selection(latitude,longitude)""",
                [west, east, south, north],
            )
        excluded: list[str] = []
        if selection.geometry and selection.country == "world" and names:
            names, excluded = drop_border_slivers(connection, selection, names)
        connection.execute("""CREATE VIEW selected_activity AS SELECT h.* FROM harmonized_cell_day h
            JOIN selected_cells s USING(cell)""")
        yield connection, len(names), excluded
    finally:
        connection.close()


def drop_border_slivers(connection, selection, names):
    """Keep the countries that really hold the polygon's cells.

    The 1:110m outlines overlap at borders, so a Peruvian department drawn by hand touches
    Bolivia or Brazil. Requiring those archives would blank its history; countries with less
    than `BORDER_SLIVER_SHARE` of the selected cells are left out and reported instead.
    """
    shares = dict(connection.execute("SELECT country,count(*) FROM selected_cells GROUP BY 1").fetchall())
    total = sum(shares.values())
    if total:
        kept = [name for name in names if shares.get(name, 0) / total >= BORDER_SLIVER_SHARE]
    else:  # No fire cell inside the polygon: keep the country that covers most of it.
        geometry = shapely.geometry.shape(selection.geometry)
        path = ROOT / "web/public/assets/countries.geojson"
        areas = {
            name: geometry.intersection(shape).area
            for name, shape in country_shapes(str(path), path.stat().st_mtime_ns)
            if name in names
        }
        kept = [max(areas, key=areas.__getitem__)]
    connection.execute("DELETE FROM selected_countries")
    connection.executemany("INSERT INTO selected_countries VALUES (?)", [(n,) for n in kept])
    connection.execute(
        "DELETE FROM selected_cells WHERE country NOT IN (SELECT country FROM selected_countries)"
    )
    return kept, sorted(set(names) - set(kept))


def monthly_calendar(connection, selection, number_countries, *, as_of_year=None):
    """Monthly calendar of the selection (ADR 0005).

    - A month has a comparable `value` only when every region-day has valid support and at most
      `MAX_UNVALIDATED_SHARE` of its observed cell-days lacks a validated coefficient.
    - Its anomaly compares it with the same calendar month of every other eligible year
      (complete, standard quality, declared archive, before the snapshot year). The current
      year therefore gets anomalies too, but never enters the baseline.
    """
    snapshot_year = as_of_year or date.today().year
    first, last = date(selection.year_start, 1, 1), date(selection.year_end + 1, 1, 1)
    counts = {
        (int(y), int(m)): (float(n or 0), int(invalid), int(total))
        for y, m, n, invalid, total in connection.execute(
            """SELECT year(day),month(day),sum(active_harmonized),
                count(*) FILTER(WHERE NOT calibration_validated),count(*) FROM selected_activity
                WHERE day>=? AND day<? GROUP BY 1,2""",
            [first, last],
        ).fetchall()
    }
    columns = {row[0] for row in connection.execute("DESCRIBE support").fetchall()}
    filled = "count(*) FILTER(WHERE snpp_filled)" if "snpp_filled" in columns else "0"
    support = {
        (int(y), int(m)): (int(n), int(valid), bool(declared), bool(provisional), int(fill))
        for y, m, n, valid, declared, provisional, fill in connection.execute(
            f"""SELECT
                year(day),month(day),count(*),
                count(*) FILTER(WHERE valid_platforms=required_platforms
                AND NOT transition_day),bool_and(declared_archive),bool_or(is_provisional),{filled}
                FROM support WHERE country IN (SELECT country FROM selected_countries)
                AND day>=? AND day<? GROUP BY 1,2""",
            [first, last],
        ).fetchall()
    }
    months = []
    for year in range(selection.year_start, selection.year_end + 1):
        for month in range(1, 13):
            days = calendar.monthrange(year, month)[1]
            expected = days * number_countries
            n, invalid, total = counts.get((year, month), (0.0, 0, 0))
            archived, valid, declared, provisional, fill = support.get(
                (year, month), (0, 0, False, False, 0)
            )
            missing_scope = not expected or archived < expected
            gap = not expected or valid == 0
            complete = not missing_scope and valid == expected
            unvalidated_share = invalid / total if total else 0.0
            unvalidated = unvalidated_share > MAX_UNVALIDATED_SHARE
            value = n if complete and not unvalidated else None
            if value == 0 and not declared:
                value = None  # without a declared archive a zero is not a demonstrated zero
            status = (
                "not_available"
                if gap
                else "unvalidated_domain"
                if unvalidated
                else "incomplete_coverage"
                if missing_scope or (expected - valid) / expected > MAX_BAD_DAY_FRACTION
                else "partial_archive"
                if not declared or valid < expected
                else "provisional"
                if provisional
                else "complete"
            )
            months.append(
                {
                    "year": year,
                    "month": month,
                    "value": value,
                    "observed_activity": n if archived else None,
                    "unit": UNIT,
                    "status": status,
                    "data_gap": gap,
                    "partial_coverage": missing_scope or valid < expected or not declared,
                    "is_provisional": provisional,
                    "expected_region_days": expected,
                    "valid_region_days": valid,
                    "calendar_days": days,
                    "unvalidated_cell_days": invalid,
                    "unvalidated_share": unvalidated_share,
                    "noaa20_filled_days": fill,
                    "eligible_for_climatology": value is not None
                    and CLIMATOLOGY_FIRST_YEAR <= year < snapshot_year
                    and declared
                    and not provisional,
                    "historical_median": None,
                    "historical_n": 0,
                    "historical_p10": None,
                    "historical_p90": None,
                    "anomaly_percent": None,
                    "rank": None,
                    "rank_of": 0,
                }
            )
    for row in months:
        history = [
            m["value"]
            for m in months
            if m["month"] == row["month"]
            and m["year"] != row["year"]
            and m["eligible_for_climatology"]
        ]
        row["historical_n"] = len(history)
        if len(history) >= MIN_HISTORY_YEARS and row["value"] is not None:
            row.update(compare(row["value"], history))
    return months


def compare(value, history):
    """Median, p10–p90 band, anomaly and rank of `value` against `history`."""
    median = statistics.median(history)
    deciles = statistics.quantiles(history, n=10, method="inclusive")
    return {
        "historical_median": median,
        "historical_p10": deciles[0],
        "historical_p90": deciles[-1],
        "anomaly_percent": 100 * (value / median - 1) if median > 0 else None,
        "rank": 1 + sum(v > value for v in history),
        "rank_of": len(history) + 1,
    }


def month_to_date(connection, selection, number_countries, *, as_of_year=None):
    """Compare a month in progress with the same days of the other eligible years.

    The calendar only compares whole months, so the current month would never get a reference.
    The window is the set of days of this month, up to the last supported one, on which every
    selected region has valid support (a transition or outage day is skipped, not counted as zero).
    Each reference year is summed over exactly the same day numbers. Below
    `MIN_AGGREGATION_DAYS` valid days there is no anomaly (sampling bias).
    """
    snapshot_year = as_of_year or date.today().year
    year, month = selection.selected_year, selection.selected_month
    valid_by_day = dict(
        connection.execute(
            """SELECT day(day),count(*) FILTER(WHERE valid_platforms=required_platforms
            AND NOT transition_day) FROM support
            WHERE country IN (SELECT country FROM selected_countries)
            AND year(day)=? AND month(day)=? GROUP BY 1""",
            [year, month],
        ).fetchall()
    )
    days = sorted(d for d, valid in valid_by_day.items() if number_countries and valid == number_countries)
    if not days or len(days) >= calendar.monthrange(year, month)[1]:
        return None
    through = days[-1]
    connection.execute("CREATE OR REPLACE TEMP TABLE window_days AS SELECT unnest(?::INTEGER[]) AS d", [days])
    activity = {
        int(y): (float(n or 0), int(invalid), int(total))
        for y, n, invalid, total in connection.execute(
            """SELECT year(day),sum(active_harmonized),
            count(*) FILTER(WHERE NOT calibration_validated),count(*) FROM selected_activity
            WHERE month(day)=? AND day(day) IN (SELECT d FROM window_days) GROUP BY 1""",
            [month],
        ).fetchall()
    }
    support = {
        int(y): (int(valid), bool(declared), bool(provisional))
        for y, valid, declared, provisional in connection.execute(
            """SELECT year(day),count(*) FILTER(WHERE valid_platforms=required_platforms
            AND NOT transition_day),bool_and(declared_archive),bool_or(is_provisional) FROM support
            WHERE country IN (SELECT country FROM selected_countries)
            AND month(day)=? AND day(day) IN (SELECT d FROM window_days) GROUP BY 1""",
            [month],
        ).fetchall()
    }

    def window_value(y):
        n, invalid, total = activity.get(y, (0.0, 0, 0))
        share = invalid / total if total else 0.0
        valid = support.get(y, (0, False, False))[0]
        complete = valid == len(days) * number_countries and share <= MAX_UNVALIDATED_SHARE
        return (n if complete else None), share

    value, share = window_value(year)
    history = []
    for y in range(CLIMATOLOGY_FIRST_YEAR, snapshot_year):
        if y == year:
            continue
        candidate, _ = window_value(y)
        _, declared, provisional = support.get(y, (0, False, False))
        if candidate is not None and declared and not provisional:
            history.append(candidate)
    result = {
        "year": year,
        "month": month,
        "through_day": through,
        "valid_days": len(days),
        "value": value,
        "historical_median": None,
        "historical_n": len(history),
        "anomaly_percent": None,
        "rank": None,
        "rank_of": 0,
        "sampling_bias_warning": len(days) < MIN_AGGREGATION_DAYS,
        "unvalidated_share": share,
    }
    if value is not None and len(history) >= MIN_HISTORY_YEARS:
        comparison = compare(value, history)
        result.update({k: comparison[k] for k in ["historical_median", "rank", "rank_of"]})
        if len(days) >= MIN_AGGREGATION_DAYS:
            result["anomaly_percent"] = comparison["anomaly_percent"]
    return result


@router.post("/api/harmonized/analyses", response_model=HarmonizedAnalysis)
def create_analysis(selection: HarmonizedSelection):
    manifest, folder = published()
    payload = {
        "selection": selection.model_dump(),
        "dataset_id": manifest["id"],
        "analysis_version": ANALYSIS_VERSION,
        "validation_status": "validated" if manifest["status"] == "published" else "experimental",
    }
    identifier = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    as_of_year = int(manifest["as_of_date"][:4]) if manifest.get("as_of_date") else None
    with selection_database(selection, folder) as (connection, number_countries, excluded):
        months = monthly_calendar(connection, selection, number_countries, as_of_year=as_of_year)
        selected = next(
            m
            for m in months
            if (m["year"], m["month"]) == (selection.selected_year, selection.selected_month)
        )
        in_progress = (
            selected["value"] is None and selected["valid_region_days"] > 0 and not selected["data_gap"]
        )
        current = (
            month_to_date(connection, selection, number_countries, as_of_year=as_of_year)
            if in_progress
            else None
        )
    result = {
        "id": identifier,
        **payload,
        "unit": UNIT,
        "months": months,
        "selected": selected,
        "month_to_date": current,
        "excluded_border_countries": excluded,
        "harmonized": True,
        "synthetic": False,
        "scientifically_validated": manifest["status"] == "published",
        "grid_resolution": manifest.get("h3_resolution", 7),
        "local_cloud_opportunities": "not_reconstructed",
        "method_version": manifest["method_version"],
        "references": manifest["references"],
        "legal": manifest["legal"],
        "provenance": {
            "input_revision": manifest.get("input_revision"),
            "auxiliaries": manifest.get("auxiliaries", []),
            "gates": manifest["gates"],
            "dataset_hashes": manifest["hashes"],
            "inputs": manifest.get("inputs", []),
            "validation": manifest.get("validation", {}),
            "geographic_diagnostic": manifest.get("geographic_diagnostic", {}),
            "input_mask_method_version": manifest.get("input_mask_method_version"),
        },
        "limitations": [
            "VIIRS-equivalent detected activity; not a number of fires and not burned area.",
            "A gap or a region without support is not zero fires.",
            "Points are H3 cell centres, not new satellite detections.",
            "Local observation opportunities and cloud cover have not been reconstructed.",
            "Year-to-year error of the MODIS-era values is about ±10 % (validated strata).",
        ],
    }
    cache = DATA / "jobs/harmonized"
    cache.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(suffix=".tmp", prefix=identifier, dir=cache)
    os.close(handle)
    temporary = Path(name)
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(cache / f"{identifier}.json")
    return result


def existing(identifier):
    if not re.fullmatch(r"[a-f0-9]{24}", identifier):
        raise HTTPException(404, "Analysis not found")
    path = DATA / "jobs/harmonized" / f"{identifier}.json"
    if not path.exists():
        raise HTTPException(404, "Analysis not found")
    result = load_json(path)
    manifest, folder = published()
    if manifest["id"] != result["dataset_id"] or result.get("analysis_version") != ANALYSIS_VERSION:
        raise HTTPException(409, "The dataset changed; create the analysis again")
    return result, folder


@router.get("/api/harmonized/analyses/{identifier}", response_model=HarmonizedAnalysis)
def get_analysis(identifier: str):
    return existing(identifier)[0]


def selected_month_rows(connection, selection, *, limit=None):
    columns = (
        "cell,day,country,biome,active_harmonized,observed_active_cell_day,"
        "source_mix,is_provisional,coefficient_fallback,calibration_validated"
    )
    query = (
        "SELECT "
        + ",".join("h." + field for field in columns.split(","))
        + ",g.latitude,g.longitude,'H3_cell_center' AS representation"
        + " FROM selected_activity h JOIN selected_cells g USING(cell)"
        + " WHERE year(h.day)=? AND month(h.day)=? ORDER BY h.cell,h.day"
    )
    if limit is not None:
        query += " LIMIT ?"
    args = [selection.selected_year, selection.selected_month] + (
        [limit] if limit is not None else []
    )
    return connection.execute(query, args), columns.split(",") + [
        "latitude",
        "longitude",
        "representation",
    ]


@router.get("/api/harmonized/analyses/{identifier}/points", response_model=PointsResponse)
def points(identifier: str, limit: int = 5000):
    if not 1 <= limit <= MAX_MAP_POINTS:
        raise HTTPException(422, "The limit must be between 1 and 10000")
    result, folder = existing(identifier)
    selection = HarmonizedSelection(**result["selection"])
    with selection_database(selection, folder) as (connection, _, _excluded):
        connection.execute(
            """CREATE TEMP TABLE monthly_points AS SELECT cell,latitude,longitude,
            sum(active_harmonized) AS activity,bool_and(calibration_validated) AS validated,
            count(*) AS observed_cell_days FROM selected_activity
            JOIN selected_cells USING(cell)
            WHERE year(day)=? AND month(day)=? GROUP BY 1,2,3""",
            [selection.selected_year, selection.selected_month],
        )
        total = connection.execute("SELECT count(*) FROM monthly_points").fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM monthly_points ORDER BY hash(cell),cell LIMIT ?", [limit]
        ).fetchall()
    return {
        "analysis_id": identifier,
        "dataset_id": result["dataset_id"],
        "validation_status": result["validation_status"],
        "references": result["references"],
        "type": "FeatureCollection",
        "representation": "H3_cell_centers",
        "unit": UNIT,
        "total": total,
        "shown": len(rows),
        "sampled": total > len(rows),
        "synthetic": False,
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "cell": cell,
                    "activity": activity,
                    "calibration_validated": validated,
                    "observed_cell_days": observed,
                },
            }
            for cell, lat, lon, activity, validated, observed in rows
        ],
    }


def safe_csv(values):
    return [
        "'" + str(value)
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
        else value
        for value in values
    ]


@router.get(
    "/api/harmonized/analyses/{identifier}/exports/{kind}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string"}},
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": {"$ref": "#/components/schemas/HarmonizedAnalysis"}},
            }
        }
    },
)
def export(identifier: str, kind: Literal["series", "manifest", "package"]):
    result, folder = existing(identifier)
    if kind == "manifest":
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="NINA_{identifier}_manifest.json"'
            },
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    exported = [
        {
            **row,
            "dataset_id": result["dataset_id"],
            "method_version": result["method_version"],
            "validation_status": result["validation_status"],
            "scientifically_validated": result["scientifically_validated"],
            "citation": " | ".join(result["references"]),
            "legal": result["legal"],
        }
        for row in result["months"]
    ]
    columns = list(exported[0])
    writer.writerow(columns)
    writer.writerows(safe_csv([row[column] for column in columns]) for row in exported)
    payload = "\ufeff" + output.getvalue()
    if kind == "series":
        return Response(
            payload,
            media_type="text/csv;charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="NINA_{identifier}_series.csv"'},
        )
    exports = DATA / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(suffix=".zip", prefix="harmonized_", dir=exports)
    os.close(handle)
    path = Path(name)
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("series.csv", payload)
            archive.writestr("manifest.json", json.dumps(result, ensure_ascii=False, indent=2))
            readme = "NINA · Harmonized fire activity\n\n" + "\n".join(result["limitations"])
            readme += "\n\nValidation status: " + result["validation_status"]
            readme += "\nMethod version: " + result["method_version"]
            readme += "\n\nUnit: " + UNIT + "\nDataset: " + result["dataset_id"]
            readme += "\nSelection: " + json.dumps(result["selection"], ensure_ascii=False)
            readme += "\nGenerated: " + date.today().isoformat()
            readme += "\n\n" + result["legal"] + "\n" + "\n".join(result["references"])
            readme += (
                "\n\ncells.csv holds every cell-day of the selected month. "
                "Daily rows have strong sampling bias; do not compute daily anomalies.\n"
            )
            archive.writestr("README.md", readme)
            selection = HarmonizedSelection(**result["selection"])
            with selection_database(selection, folder) as (connection, _, _excluded):
                cursor, fields = selected_month_rows(connection, selection)
                with (
                    archive.open("cells.csv", "w") as binary,
                    io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream,
                ):
                    writer = csv.writer(stream)
                    writer.writerow(
                        fields
                        + ["sampling_bias_warning", "validation_status", "dataset_id", "unit"]
                    )
                    while rows := cursor.fetchmany(8192):
                        writer.writerows(
                            safe_csv(
                                list(row)
                                + [True, result["validation_status"], result["dataset_id"], UNIT]
                            )
                            for row in rows
                        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"NINA_{identifier}.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


class HarmonizedQuestion(BaseModel):
    analysis_id: str = Field(min_length=24, max_length=24)
    question: str = Field(min_length=1, max_length=600)
    language: Literal["en", "es"] = "en"


ANSWERS = {
    "en": {
        "value": "{period} has {value:,.0f} VIIRS-equivalent active cell-days.",
        "no_value": "{period} has no comparable value ({status}).",
        "median": (
            " The median of the same month in {n} other eligible years is {median:,.0f}"
            " ({anomaly:+.1f} %); it ranks {rank} of {rank_of}."
        ),
        "no_median": " There is no eligible comparison of at least five years for this month.",
        "coverage": (
            "The month's status is {status}: {valid} of {expected} region-days have valid support"
            "{filled}. This describes archive support; it does not reconstruct clouds or local"
            " observation opportunities."
        ),
        "filled": ", {days} of them filled from NOAA-20 through the validated bridge",
        "method": (
            "The unit is one active H3 cell (about 5 km²) per day on a VIIRS S-NPP-equivalent scale."
            " MODIS is converted with coefficients trained on 2012–2025 and validated on held-out"
            " years; NOAA-20 is bridged to S-NPP. An adjusted unit is not a new fire location."
        ),
        "scope": (
            "This analysis gives context on detected activity. It contains no spread, cause or"
            " forecast model that could answer that question."
        ),
        "partial": " The archive is partial: the figure does not certify the total of the area.",
        "footer": " These values describe detected activity, not individual fires, burned area or spread.",
        "experimental": "Experimental result. ",
    },
    "es": {
        "value": "{period} tiene {value:,.0f} celdas-día activas equivalentes VIIRS.",
        "no_value": "{period} no tiene un valor comparable ({status}).",
        "median": (
            " La mediana del mismo mes en otros {n} años elegibles es {median:,.0f}"
            " ({anomaly:+.1f} %); ocupa el puesto {rank} de {rank_of}."
        ),
        "no_median": " No hay una comparación elegible de al menos cinco años para este mes.",
        "coverage": (
            "El estado del mes es {status}: {valid} de {expected} combinaciones región/día tienen"
            " soporte válido{filled}. Esto describe el archivo; no reconstruye nubes ni"
            " oportunidades locales de observación."
        ),
        "filled": ", {days} completadas con NOAA-20 mediante el puente validado",
        "method": (
            "La unidad es una celda H3 activa (unos 5 km²) por día, en escala equivalente a VIIRS"
            " S-NPP. MODIS se convierte con coeficientes entrenados en 2012–2025 y validados con"
            " años reservados; NOAA-20 se enlaza con S-NPP. Una unidad ajustada no es un fuego nuevo."
        ),
        "scope": (
            "Este análisis aporta contexto de actividad detectada. No contiene un modelo de"
            " propagación, causas ni pronóstico que responda esa pregunta."
        ),
        "partial": " El archivo es parcial: la cifra no certifica el total del área.",
        "footer": " Estos valores describen actividad detectada, no incendios individuales, área quemada ni propagación.",
        "experimental": "Resultado experimental. ",
    },
}
COVERAGE_TERMS = ["coverage", "cloud", "quality", "reliab", "cobertura", "nube", "calidad", "fiable"]
METHOD_TERMS = ["sensor", "modis", "viirs", "harmoniz", "armoniz", "method", "método"]
SCOPE_TERMS = ["evac", "tomorrow", "mañana", "predict", "predic", "forecast", "cause", "causa", "spread", "propaga"]


@router.post("/api/harmonized/assistant", response_model=AssistantResponse)
def assistant(question: HarmonizedQuestion):
    result, _ = existing(question.analysis_id)
    text_for = ANSWERS[question.language]
    selected = result["selected"]
    period = f"{selected['year']}-{selected['month']:02d}"
    if selected["value"] is not None:
        answer = text_for["value"].format(period=period, value=selected["value"])
    else:
        answer = text_for["no_value"].format(period=period, status=selected["status"])
    if selected["historical_median"] is not None and selected["anomaly_percent"] is not None:
        answer += text_for["median"].format(
            n=selected["historical_n"],
            median=selected["historical_median"],
            anomaly=selected["anomaly_percent"],
            rank=selected["rank"],
            rank_of=selected["rank_of"],
        )
    else:
        answer += text_for["no_median"]
    text = question.question.lower()
    if any(term in text for term in COVERAGE_TERMS):
        filled = selected.get("noaa20_filled_days", 0)
        answer = text_for["coverage"].format(
            status=selected["status"],
            valid=selected["valid_region_days"],
            expected=selected["expected_region_days"],
            filled=text_for["filled"].format(days=filled) if filled else "",
        )
    elif any(term in text for term in METHOD_TERMS):
        answer = text_for["method"]
    elif any(term in text for term in SCOPE_TERMS):
        answer = text_for["scope"]
    if selected["partial_coverage"]:
        answer += text_for["partial"]
    answer += text_for["footer"]
    if not result["scientifically_validated"]:
        answer = text_for["experimental"] + answer
    return {
        "answer": answer,
        "analysis_id": result["id"],
        "dataset_id": result["dataset_id"],
        "facts": selected,
        "references": result["references"],
        "mode": "deterministic_grounded",
        "external_llm_used": False,
    }
