"""Monthly climate context per Peruvian department from NASA POWER (2001-2025).

Context layer only: it states the hydro-climatic setting of a period (precipitation and
vapour-pressure-deficit anomalies). It does not attribute fire activity to climate.

Source: NASA POWER monthly point API (``/api/temporal/monthly/point``, community ``AG``),
meteorology from MERRA-2 at its native 0.5 deg x 0.625 deg grid.

Pipeline
--------
1. A regular 0.5 deg grid over Peru's bounding box is filtered to the points that lie inside, or
   within 0.5 deg of, the union of the geoBoundaries ADM1 polygons.
2. Each point is requested once (sequentially, with a polite delay, retries and exponential
   backoff) and cached verbatim under ``source/auxiliary/power/monthly/``.
3. Per point and month: precipitation total (mm) = POWER monthly mean rate (mm/day) x days in
   the month; VPD (kPa) from monthly mean T2M and RH2M with the Tetens equation (FAO-56 eq. 11).
4. Department value = mean over the grid points inside the polygon, counting each POWER source
   cell once (a 0.5 deg grid oversamples the 0.625 deg MERRA-2 longitude spacing, so about one
   point in five repeats a cell). Departments without any interior point use the
   grid points inside Peru (never offshore or foreign) within ``FALLBACK_RADIUS_DEG`` of the
   polygon, or the single nearest one if none is that close.
5. Anomalies per department and calendar month against the 2002-2024 climatology: z-scores of
   precipitation and VPD (sample standard deviation), the empirical percentile of precipitation
   among the climatology years, and ``drought = precip_z <= -1 and vpd_z >= +1``.

Run from ``packages/nina``::

    uv run python -m nina.io.climate --workspace ../..             # build from the cache
    uv run python -m nina.io.climate --workspace ../.. --download  # fetch missing points first
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import ssl
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
import truststore
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from nina.io.harmonization import file_digest, log, read_json, write_json

POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
POWER_DOCS = "https://power.larc.nasa.gov/docs/services/api/temporal/monthly/"
COMMUNITY = "AG"
PARAMETERS = ("PRECTOTCORR", "T2M", "T2M_MAX", "RH2M")
FIRST_YEAR, LAST_YEAR = 2001, 2025
CLIMATOLOGY_YEARS = (2002, 2024)
BBOX = (-81.5, -18.5, -68.5, 0.0)  # lon_min, lat_min, lon_max, lat_max (deg)
GRID_STEP_DEG = 0.5
BUFFER_DEG = 0.5
FALLBACK_RADIUS_DEG = 0.5  # one grid step
REQUEST_DELAY_S = 1.0
MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 2.0
TIMEOUT_S = 120.0
CACHE_SCHEMA = 1
DROUGHT_PRECIP_Z = -1.0
DROUGHT_VPD_Z = 1.0
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
AMAZON_DEPARTMENTS = ("Ucayali", "Loreto", "San Martín", "Amazonas", "Madre de Dios")
AMAZON_DROUGHT_YEARS = (2005, 2010, 2016, 2023, 2024)
AMAZON_DROUGHT_MONTHS = (8, 9)

BOUNDARIES = Path("data/boundaries/departments.geojson")
CACHE_DIR = Path("source/auxiliary/power/monthly")
OUTPUT_DIR = Path("source/context/climate")
OUTPUT_FILE = "climate_department_month.parquet"

OUTPUT_SCHEMA = pa.schema(
    [
        ("department", pa.string()),
        ("department_key", pa.string()),
        ("year", pa.int32()),
        ("month", pa.int32()),
        ("precip_mm", pa.float64()),
        ("t2m_c", pa.float64()),
        ("t2m_max_c", pa.float64()),
        ("rh_pct", pa.float64()),
        ("vpd_kpa", pa.float64()),
        ("precip_z", pa.float64()),
        ("vpd_z", pa.float64()),
        ("precip_percentile", pa.float64()),
        ("drought", pa.bool_()),
        ("n_points", pa.int32()),
    ]
)

Sleep = Callable[[float], None]


# --------------------------------------------------------------------------- pure helpers


def saturation_vapour_pressure_kpa(t_c: Any) -> Any:
    """Tetens saturation vapour pressure over water, FAO-56 eq. 11 (kPa, T in deg C)."""
    return 0.6108 * np.exp(17.27 * np.asarray(t_c, dtype=float) / (np.asarray(t_c) + 237.3))


def vapour_pressure_deficit_kpa(t_c: Any, rh_pct: Any) -> Any:
    """VPD = e_s(T) * (1 - RH/100), with e_s from Tetens (kPa)."""
    rh = np.clip(np.asarray(rh_pct, dtype=float), 0.0, 100.0)
    return saturation_vapour_pressure_kpa(t_c) * (1.0 - rh / 100.0)


def department_key(name: str) -> str:
    """Uppercase ASCII key without accents and with single spaces ("San Martín" -> "SAN MARTIN")."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


def point_id(lat: float, lon: float) -> str:
    """Stable, filesystem-safe identifier of a grid point."""
    return f"lat{lat:+06.2f}_lon{lon:+07.2f}"


def grid_points(
    bbox: tuple[float, float, float, float] = BBOX, step: float = GRID_STEP_DEG
) -> pd.DataFrame:
    """Regular grid (inclusive bounds) built from integer steps to avoid float drift."""
    lon_min, lat_min, lon_max, lat_max = bbox
    n_lon = round((lon_max - lon_min) / step) + 1
    n_lat = round((lat_max - lat_min) / step) + 1
    rows = [
        (round(lat_min + j * step, 4), round(lon_min + i * step, 4))
        for j in range(n_lat)
        for i in range(n_lon)
    ]
    frame = pd.DataFrame(rows, columns=["lat", "lon"])
    frame.insert(0, "point_id", [point_id(lat, lon) for lat, lon in rows])
    return frame


def load_departments(path: Path) -> dict[str, BaseGeometry]:
    """geoBoundaries ADM1 polygons keyed by ``shapeName`` (made valid)."""
    collection = read_json(path)
    departments: dict[str, BaseGeometry] = {}
    for feature in collection["features"]:
        name = str(feature["properties"]["shapeName"]).strip()
        departments[name] = shapely.make_valid(shape(feature["geometry"]))
    return dict(sorted(departments.items()))


def select_points(
    grid: pd.DataFrame, departments: Mapping[str, BaseGeometry], buffer_deg: float = BUFFER_DEG
) -> pd.DataFrame:
    """Keep grid points inside or within ``buffer_deg`` of the union; tag the containing polygon.

    ``department`` is the first polygon (alphabetical) that intersects the point, or ``None`` for
    buffer points outside every polygon (kept for the record, not used in averages).
    """
    union = shapely.union_all(list(departments.values()))
    near = shapely.intersects_xy(union.buffer(buffer_deg), grid["lon"], grid["lat"])
    kept = grid.loc[near].reset_index(drop=True).copy()
    owner = np.full(len(kept), None, dtype=object)
    for name, geometry in departments.items():
        inside = shapely.intersects_xy(geometry, kept["lon"], kept["lat"])
        owner[inside & pd.isna(owner)] = name
    kept["department"] = owner
    return kept


def assign_points(
    points: pd.DataFrame,
    departments: Mapping[str, BaseGeometry],
    radius_deg: float = FALLBACK_RADIUS_DEG,
) -> pd.DataFrame:
    """Map each department to the grid points that represent it.

    Interior points first (``method = "inside"``). A department without interior points (a polygon
    smaller than a grid cell) takes the grid points inside Peru whose planar distance to its
    polygon is at most ``radius_deg``, or the single nearest one if none is that close
    (``method = "nearest"``). Degrees are nearly isotropic at 0-18 deg S (cos(lat) >= 0.95).
    """
    land = points.loc[points["department"].notna()].reset_index(drop=True)
    land_geoms = shapely.points(land["lon"].to_numpy(), land["lat"].to_numpy())
    rows: list[dict[str, Any]] = []
    for name, geometry in departments.items():
        inside = land.loc[land["department"] == name, "point_id"].tolist()
        if inside:
            rows += [{"department": name, "point_id": p, "method": "inside"} for p in inside]
            continue
        distance = shapely.distance(geometry, land_geoms)
        order = np.lexsort((land["point_id"].to_numpy(), distance))
        chosen = [i for i in order if distance[i] <= radius_deg] or [order[0]]
        rows += [
            {
                "department": name,
                "point_id": land.at[int(i), "point_id"],
                "method": "nearest",
                "distance_deg": float(distance[i]),
            }
            for i in chosen
        ]
    return pd.DataFrame(rows)


def parse_power_record(record: Mapping[str, Any]) -> pd.DataFrame:
    """Monthly rows (year, month, raw POWER values) from a cached POWER response; ANN dropped."""
    response = record["response"]
    fill = float(response.get("header", {}).get("fill_value", -999.0))
    values = response["properties"]["parameter"]
    frames = []
    for parameter in PARAMETERS:
        series = pd.Series(values[parameter], name=parameter, dtype=float)
        frames.append(series.where(series != fill))
    frame = pd.concat(frames, axis=1)
    frame.index = frame.index.astype(str)
    frame = frame.loc[frame.index.str[-2:] != "13"]
    frame.insert(0, "year", frame.index.str[:4].astype(int))
    frame.insert(1, "month", frame.index.str[4:6].astype(int))
    frame = frame.loc[frame["year"].between(FIRST_YEAR, LAST_YEAR)]
    return frame.reset_index(drop=True)


def series_fingerprint(record: Mapping[str, Any]) -> str:
    """Hash of the returned values: identical series come from the same POWER source cell."""
    values = record["response"]["properties"]["parameter"]
    payload = json.dumps({p: values[p] for p in PARAMETERS}, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def point_values(records: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Per point and month: physical variables in output units plus the source-cell fingerprint."""
    frames = []
    for pid, record in records.items():
        raw = parse_power_record(record)
        months = zip(raw["year"], raw["month"], strict=True)
        days = [calendar.monthrange(y, m)[1] for y, m in months]
        frames.append(
            pd.DataFrame(
                {
                    "point_id": pid,
                    "source_cell": series_fingerprint(record),
                    "year": raw["year"],
                    "month": raw["month"],
                    "precip_mm": raw["PRECTOTCORR"] * np.asarray(days, dtype=float),
                    "t2m_c": raw["T2M"],
                    "t2m_max_c": raw["T2M_MAX"],
                    "rh_pct": raw["RH2M"],
                    "vpd_kpa": vapour_pressure_deficit_kpa(raw["T2M"], raw["RH2M"]),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


VALUE_COLUMNS = ["precip_mm", "t2m_c", "t2m_max_c", "rh_pct", "vpd_kpa"]


def department_means(values: pd.DataFrame, assignment: pd.DataFrame) -> pd.DataFrame:
    """Department x month means, each distinct source cell counted once.

    ``t2m_max_c`` is the mean over cells of each cell's monthly maximum. ``n_points`` counts the
    grid points assigned to the department (``n_cells`` the distinct source cells behind them).
    """
    joined = assignment[["department", "point_id"]].merge(values, on="point_id", how="inner")
    unique = joined.drop_duplicates(["department", "source_cell", "year", "month"])
    means = unique.groupby(["department", "year", "month"], as_index=False)[VALUE_COLUMNS].mean()
    counts = assignment.groupby("department").agg(n_points=("point_id", "nunique")).reset_index()
    cells = joined.groupby("department").agg(n_cells=("source_cell", "nunique")).reset_index()
    return means.merge(counts, on="department").merge(cells, on="department")


def climatology_scores(
    values: pd.Series, years: pd.Series, period: tuple[int, int] = CLIMATOLOGY_YEARS
) -> tuple[pd.Series, pd.Series]:
    """z-score and empirical percentile (0-100) of each value against the period's values.

    z uses the sample standard deviation (ddof = 1); it is NaN when that deviation is 0 or fewer
    than two reference years exist. Percentile = 100 * (#ref < x + 0.5 * #ref == x) / #ref, i.e.
    the "mean" percentile rank, with ties split.
    """
    reference = values[years.between(*period)].dropna().to_numpy(dtype=float)
    data = values.to_numpy(dtype=float)
    if reference.size > 1 and float(np.std(reference, ddof=1)) > 0:
        z = (data - reference.mean()) / np.std(reference, ddof=1)
    else:
        z = np.full(data.shape, np.nan)
    if reference.size:
        below = (reference[None, :] < data[:, None]).sum(axis=1)
        equal = (reference[None, :] == data[:, None]).sum(axis=1)
        percentile = 100.0 * (below + 0.5 * equal) / reference.size
        percentile = np.where(np.isnan(data), np.nan, percentile)
    else:
        percentile = np.full(data.shape, np.nan)
    return pd.Series(z, index=values.index), pd.Series(percentile, index=values.index)


def add_anomalies(frame: pd.DataFrame, period: tuple[int, int] = CLIMATOLOGY_YEARS) -> pd.DataFrame:
    """Adds ``precip_z``, ``vpd_z``, ``precip_percentile`` and the nullable ``drought`` flag."""
    result = frame.copy()
    for column in ("precip_z", "vpd_z", "precip_percentile"):
        result[column] = np.nan
    for _, group in result.groupby(["department", "month"]):
        precip_z, percentile = climatology_scores(group["precip_mm"], group["year"], period)
        vpd_z, _ = climatology_scores(group["vpd_kpa"], group["year"], period)
        result.loc[group.index, "precip_z"] = precip_z
        result.loc[group.index, "vpd_z"] = vpd_z
        result.loc[group.index, "precip_percentile"] = percentile
    defined = result["precip_z"].notna() & result["vpd_z"].notna()
    flag = (result["precip_z"] <= DROUGHT_PRECIP_Z) & (result["vpd_z"] >= DROUGHT_VPD_Z)
    result["drought"] = pd.array(np.where(defined, flag, pd.NA), dtype="boolean")
    return result


def output_table(frame: pd.DataFrame) -> pa.Table:
    """Final column order and Arrow types (VARCHAR, INTEGER, DOUBLE, BOOLEAN in DuckDB)."""
    table = frame.assign(department_key=frame["department"].map(department_key))
    table = table.sort_values(["department", "year", "month"]).reset_index(drop=True)
    return pa.Table.from_pandas(
        table[OUTPUT_SCHEMA.names], schema=OUTPUT_SCHEMA, preserve_index=False
    )


def known_drought_check(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Amazon departments in Aug-Sep of documented Amazon drought years (no tuning applied)."""
    subset = frame.loc[
        frame["department"].isin(AMAZON_DEPARTMENTS)
        & frame["year"].isin(AMAZON_DROUGHT_YEARS)
        & frame["month"].isin(AMAZON_DROUGHT_MONTHS)
    ].sort_values(["department", "year", "month"])

    def number(value: Any, digits: int) -> float | None:
        return None if pd.isna(value) else round(float(value), digits)

    rows = []
    for row in subset.itertuples(index=False):
        drought = row.drought
        rows.append(
            {
                "department": row.department,
                "year": int(row.year),
                "month": int(row.month),
                "precip_mm": number(row.precip_mm, 1),
                "precip_z": number(row.precip_z, 2),
                "precip_percentile": number(row.precip_percentile, 1),
                "vpd_kpa": number(row.vpd_kpa, 3),
                "vpd_z": number(row.vpd_z, 2),
                "drought": None if pd.isna(drought) else bool(drought),
            }
        )
    return rows


# --------------------------------------------------------------------------- HTTP and cache


def request_params(lat: float, lon: float) -> dict[str, Any]:
    """Query string of one POWER monthly point request."""
    return {
        "parameters": ",".join(PARAMETERS),
        "community": COMMUNITY,
        "longitude": lon,
        "latitude": lat,
        "start": FIRST_YEAR,
        "end": LAST_YEAR,
        "format": "JSON",
    }


def cache_path(cache_dir: Path, lat: float, lon: float) -> Path:
    """One JSON file per grid point."""
    return cache_dir / f"{point_id(lat, lon)}.json"


def make_client() -> httpx.Client:
    """System certificates (truststore); no credentials are needed by POWER."""
    return httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        timeout=TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": "nina-climate-context/1.0 (python-httpx)"},
    )


def valid_record(record: Any, params: Mapping[str, Any]) -> bool:
    """A cache entry is reusable only for the same query and with every parameter present."""
    try:
        values = record["response"]["properties"]["parameter"]
        return (
            record.get("cache_schema") == CACHE_SCHEMA
            and record["request"]["params"] == json.loads(json.dumps(dict(params)))
            and all(p in values and values[p] for p in PARAMETERS)
        )
    except (KeyError, TypeError):
        return False


def retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Exponential backoff, honouring a numeric ``Retry-After`` header when present."""
    if response is not None:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return float(header)
    return BACKOFF_BASE_S * 2**attempt


def fetch_point(
    client: httpx.Client,
    lat: float,
    lon: float,
    cache_dir: Path,
    *,
    sleep: Sleep | None = None,
) -> tuple[dict[str, Any], bool]:
    """Cached POWER record for one point; returns ``(record, downloaded)``.

    Retries transport errors and 408/425/429/5xx with exponential backoff; a 4xx such as 422
    (invalid request) fails immediately. The cache file is written atomically and stores the
    request, the retrieval time and the API name/version reported by POWER.
    """
    path = cache_path(cache_dir, lat, lon)
    params = request_params(lat, lon)
    if path.exists():
        record = read_json(path)
        if valid_record(record, params):
            return record, False
    last_error = "no attempt"
    for attempt in range(MAX_ATTEMPTS):
        response: httpx.Response | None = None
        try:
            response = client.get(POWER_URL, params=params)
            if response.status_code == httpx.codes.OK:
                payload = response.json()
                record = {
                    "cache_schema": CACHE_SCHEMA,
                    "request": {"url": POWER_URL, "params": params},
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "api": payload.get("header", {}).get("api", {}),
                    "response": payload,
                }
                if not valid_record(record, params):
                    raise ValueError("POWER response lacks requested parameters")
                write_json(path, record)
                return record, True
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRY_STATUS:
                break
        except (httpx.TransportError, ValueError) as error:
            last_error = f"{type(error).__name__}: {error}"
        if attempt + 1 < MAX_ATTEMPTS:
            (sleep or time.sleep)(retry_delay(response, attempt))
    raise RuntimeError(f"POWER request failed for {point_id(lat, lon)}: {last_error}")


def download_points(
    points: pd.DataFrame,
    cache_dir: Path,
    *,
    client_factory: Callable[[], httpx.Client] | None = None,
    delay_s: float = REQUEST_DELAY_S,
    sleep: Sleep | None = None,
) -> dict[str, int]:
    """Sequential download of the points missing from the cache, pausing after each request.

    ``client_factory`` and ``sleep`` default to :func:`make_client` and :func:`time.sleep`,
    resolved at call time so tests can monkeypatch them.
    """
    pause = sleep or time.sleep
    downloaded = cached = 0
    with (client_factory or make_client)() as client:
        for index, row in enumerate(points.itertuples(index=False), start=1):
            _, fresh = fetch_point(client, row.lat, row.lon, cache_dir, sleep=pause)
            if fresh:
                downloaded += 1
                pause(delay_s)
                if downloaded % 25 == 0:
                    log("power_progress", done=index, total=len(points), downloaded=downloaded)
            else:
                cached += 1
    return {"downloaded": downloaded, "cached": cached}


def load_cache(points: pd.DataFrame, cache_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Valid cached records keyed by point id, plus the ids still missing."""
    records: dict[str, Any] = {}
    missing: list[str] = []
    for row in points.itertuples(index=False):
        path = cache_path(cache_dir, row.lat, row.lon)
        record = read_json(path) if path.exists() else None
        if record is not None and valid_record(record, request_params(row.lat, row.lon)):
            records[row.point_id] = record
        else:
            missing.append(row.point_id)
    return records, missing


def cache_digest(paths: Iterable[Path]) -> str:
    """SHA-256 over the sorted ``name:sha256`` lines of the cache files used."""
    lines = sorted(f"{p.name}:{file_digest(p)}" for p in paths)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- build


METHOD = {
    "precip_mm": "POWER PRECTOTCORR monthly mean rate (mm/day) x days in the month",
    "t2m_c": "POWER T2M monthly mean (deg C)",
    "t2m_max_c": (
        "POWER T2M_MAX monthly value, which is the highest daily maximum of the month (checked "
        "against the daily API), averaged over source cells"
    ),
    "rh_pct": "POWER RH2M monthly mean (%)",
    "vpd_kpa": (
        "Per point: es = 0.6108 * exp(17.27 * T / (T + 237.3)) kPa (Tetens, FAO-56 eq. 11) with "
        "T = monthly mean T2M; VPD = es * (1 - RH2M/100); then averaged over source cells. "
        "Computed from monthly means, so it underestimates the mean of daily VPD"
    ),
    "department_value": (
        "Mean over grid points inside the polygon, each distinct POWER source cell counted once "
        "(identical value series = same MERRA-2 cell)"
    ),
    "fallback": (
        "Departments with no interior point use the grid points inside Peru within "
        f"{FALLBACK_RADIUS_DEG} deg (planar) of the polygon, or the single nearest one if none"
    ),
    "z_score": (
        "(x - mean) / sd per department and calendar month over the climatology years; sd with "
        "ddof = 1; NaN when sd = 0"
    ),
    "precip_percentile": (
        "100 * (#years below + 0.5 * #ties) / #years, against the climatology years of the same "
        "department and calendar month (0-100)"
    ),
    "drought": (
        f"precip_z <= {DROUGHT_PRECIP_Z} and vpd_z >= {DROUGHT_VPD_Z}; null if a z is undefined"
    ),
    "scope": "Climate context only; no causal attribution of fire activity",
}


def build(workspace: Path, *, download: bool = False) -> dict[str, Any]:
    """Select points, (optionally) download, aggregate, score and write Parquet + manifest."""
    boundaries = workspace / BOUNDARIES
    cache_dir = workspace / CACHE_DIR
    output_dir = workspace / OUTPUT_DIR
    departments = load_departments(boundaries)
    points = select_points(grid_points(), departments)
    log(
        "power_plan",
        grid_points=len(grid_points()),
        kept_points=len(points),
        land_points=int(points["department"].notna().sum()),
        departments=len(departments),
    )
    if download:
        log("power_download", **download_points(points, cache_dir))
    records, missing = load_cache(points, cache_dir)
    if missing:
        log("power_cache_incomplete", missing=len(missing), example=missing[:5])
        raise SystemExit(2)

    assignment = assign_points(points, departments)
    values = point_values(records)
    frame = add_anomalies(department_means(values, assignment))
    table = output_table(frame)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet = output_dir / OUTPUT_FILE
    temporary = parquet.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary)
    temporary.replace(parquet)

    by_department = frame.groupby("department").first()
    department_rows = []
    for name in departments:
        rows = assignment.loc[assignment["department"] == name]
        department_rows.append(
            {
                "department": name,
                "department_key": department_key(name),
                "method": str(rows["method"].iloc[0]),
                "n_points": int(by_department.at[name, "n_points"]),
                "n_source_cells": int(by_department.at[name, "n_cells"]),
                "point_ids": sorted(rows["point_id"].tolist()),
            }
        )
    api_versions = sorted({str(r.get("api", {}).get("version")) for r in records.values()})
    retrieved = sorted(str(r["retrieved_at"]) for r in records.values())
    sample = next(iter(records.values()))["response"]
    used_files = [cache_path(cache_dir, r.lat, r.lon) for r in points.itertuples(index=False)]
    sanity = known_drought_check(frame)
    manifest = {
        "product": "climate_department_month",
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": "Monthly climate context per Peruvian department; no causal attribution",
        "source": {
            "name": "NASA POWER (Prediction Of Worldwide Energy Resources)",
            "endpoint": POWER_URL,
            "documentation": POWER_DOCS,
            "community": COMMUNITY,
            "api_name": sample.get("header", {}).get("api", {}).get("name"),
            "api_versions": api_versions,
            "upstream_sources": sample.get("header", {}).get("sources"),
            "time_standard": sample.get("header", {}).get("time_standard"),
            "fill_value": sample.get("header", {}).get("fill_value"),
            "retrieved_first": retrieved[0],
            "retrieved_last": retrieved[-1],
            "citation": (
                "These data were obtained from the NASA Langley Research Center (LaRC) POWER "
                "Project funded through the NASA Earth Science/Applied Science Program."
            ),
        },
        "parameters": {p: sample.get("parameters", {}).get(p, {}) for p in PARAMETERS},
        "years": [FIRST_YEAR, LAST_YEAR],
        "grid": {
            "bbox_lon_lat": list(BBOX),
            "step_deg": GRID_STEP_DEG,
            "buffer_deg": BUFFER_DEG,
            "candidate_points": len(grid_points()),
            "kept_points": len(points),
            "land_points": int(points["department"].notna().sum()),
            "distinct_source_cells": int(values["source_cell"].nunique()),
            "native_resolution": "MERRA-2 0.5 deg lat x 0.625 deg lon",
        },
        "boundaries": {
            "path": BOUNDARIES.as_posix(),
            "source": "geoBoundaries gbOpen PER ADM1",
            "sha256": file_digest(boundaries),
        },
        "climatology_years": list(CLIMATOLOGY_YEARS),
        "method": METHOD,
        "outputs": {
            "parquet": (OUTPUT_DIR / OUTPUT_FILE).as_posix(),
            "rows": table.num_rows,
            "schema": {f.name: str(f.type) for f in OUTPUT_SCHEMA},
            "sha256": file_digest(parquet),
        },
        "hashes": {
            "power_cache_sha256": cache_digest(used_files),
            "code_sha256": file_digest(Path(__file__)),
        },
        "departments": department_rows,
        "drought_months": int(frame["drought"].fillna(False).sum()),
        "sanity_check_amazon_drought_years": sanity,
    }
    write_json(output_dir / "manifest.json", manifest)
    log("climate_written", rows=table.num_rows, path=str(parquet))
    return manifest


def main() -> None:
    """Without --download, builds from the cache and exits with code 2 if points are missing."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true", help="fetch points missing from cache")
    args = parser.parse_args()
    manifest = build(args.workspace.resolve(), download=args.download)
    for row in manifest["sanity_check_amazon_drought_years"]:
        log("sanity", **row)


if __name__ == "__main__":
    main()
