"""Consultas de artefactos comunes publicados. La API no calibra sensores."""

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
import shapely
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
ANALYSIS_VERSION = "1"
MAX_GEOMETRY_BYTES = 100000
MAX_LONGITUDE = 180
MAX_LATITUDE = 90
CLIMATOLOGY_FIRST_YEAR = 2001
MAX_BAD_DAY_FRACTION = 0.20
MIN_HISTORY_YEARS = 5
MAX_MAP_POINTS = 10000


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
            raise ValueError("El año seleccionado debe estar dentro del rango")
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
                raise ValueError("Polígono WGS84 inválido") from error
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
    eligible_for_climatology: bool
    historical_median: float | None
    historical_n: int
    anomaly_percent: float | None


class HarmonizedAnalysis(BaseModel):
    id: str
    selection: HarmonizedSelection
    dataset_id: str
    analysis_version: str
    unit: str
    months: list[CalendarMonth]
    selected: CalendarMonth
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
                "message": "La serie armonizada todavía no supera la validación.",
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
        raise HTTPException(409, "No existe un producto aprobado")
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
        raise HTTPException(503, "El producto publicado está incompleto")
    if load_json(folder / "manifest.json") != manifest:
        raise HTTPException(503, "El manifiesto del producto no coincide con su publicación")
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
        raise HTTPException(503, "Falló la verificación de integridad del producto") from None
    return manifest, folder


@lru_cache(maxsize=4)
def verify_files(signature):
    for name, expected, _, _ in signature:
        digest = hashlib.sha256()
        with Path(name).open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("Hash inválido")


def selected_countries(selection):
    features = load_json(ROOT / "web/public/assets/countries.geojson")["features"]
    if selection.country != "world":
        features = [f for f in features if f["properties"]["name"] == selection.country]
        if not features:
            raise HTTPException(422, "País desconocido; usa los nombres de /api/places")
    if selection.geometry:
        geometry = shapely.geometry.shape(selection.geometry)
        features = [
            f for f in features if geometry.intersects(shapely.geometry.shape(f["geometry"]))
        ]
    names = [f["properties"]["name"] for f in features]
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
        connection.execute("""CREATE VIEW selected_activity AS SELECT h.* FROM harmonized_cell_day h
            JOIN selected_cells s USING(cell)""")
        yield connection, len(names)
    finally:
        connection.close()


def monthly_calendar(connection, selection, number_countries, *, as_of_year=None):
    snapshot_year = as_of_year or date.today().year
    first, last = date(selection.year_start, 1, 1), date(selection.year_end + 1, 1, 1)
    counts = {
        (int(y), int(m)): (float(n or 0), int(invalid))
        for y, m, n, invalid in connection.execute(
            """SELECT year(day),month(day),sum(active_harmonized),
                count(*) FILTER(WHERE NOT calibration_validated) FROM selected_activity
                WHERE day>=? AND day<? GROUP BY 1,2""",
            [first, last],
        ).fetchall()
    }
    support = {
        (int(y), int(m)): (int(n), int(valid), bool(declared), bool(provisional))
        for y, m, n, valid, declared, provisional in connection.execute(
            """SELECT
                year(day),month(day),count(*),
                count(*) FILTER(WHERE valid_platforms=required_platforms
                AND NOT transition_day),bool_and(declared_archive),bool_or(is_provisional)
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
            n, invalid = counts.get((year, month), (0.0, 0))
            archived, valid, declared, provisional = support.get(
                (year, month), (0, 0, False, False)
            )
            missing_scope = not expected or archived < expected
            gap = not expected or valid == 0
            bad_fraction = 1 - valid / expected if expected else 1
            eligible = (
                year >= CLIMATOLOGY_FIRST_YEAR
                and year < snapshot_year
                and not missing_scope
                and bad_fraction <= MAX_BAD_DAY_FRACTION
                and declared
                and not provisional
                and invalid == 0
            )
            value = (
                None
                if gap or missing_scope or invalid or bad_fraction > MAX_BAD_DAY_FRACTION
                else n
            )
            if value == 0 and (not declared or valid < expected):
                value = None
            status = (
                "not_available"
                if gap
                else "unvalidated_domain"
                if invalid
                else "incomplete_coverage"
                if missing_scope or bad_fraction > MAX_BAD_DAY_FRACTION
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
                    "eligible_for_climatology": eligible,
                    "historical_median": None,
                    "historical_n": 0,
                    "anomaly_percent": None,
                }
            )
    for row in months:
        history = [
            m["value"]
            for m in months
            if m["month"] == row["month"]
            and m["year"] < row["year"]
            and m["eligible_for_climatology"]
            and m["value"] is not None
        ]
        row["historical_n"] = len(history)
        if (
            len(history) >= MIN_HISTORY_YEARS
            and row["value"] is not None
            and row["eligible_for_climatology"]
        ):
            median = statistics.median(history)
            row["historical_median"] = median
            row["anomaly_percent"] = 100 * (row["value"] / median - 1) if median > 0 else None
    return months


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
    with selection_database(selection, folder) as (connection, number_countries):
        months = monthly_calendar(
            connection,
            selection,
            number_countries,
            as_of_year=int(manifest["as_of_date"][:4]) if manifest.get("as_of_date") else None,
        )
    selected = next(
        m
        for m in months
        if (m["year"], m["month"]) == (selection.selected_year, selection.selected_month)
    )
    result = {
        "id": identifier,
        **payload,
        "unit": UNIT,
        "months": months,
        "selected": selected,
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
            "Actividad detectada equivalente; no es número de incendios ni área quemada.",
            "Un hueco o una región sin soporte no equivale a cero incendios.",
            "Los puntos representan centros de celdas, no nuevas detecciones satelitales.",
            "No se han reconstruido las oportunidades locales de observación ni la nubosidad.",
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
        raise HTTPException(404, "Análisis no encontrado")
    path = DATA / "jobs/harmonized" / f"{identifier}.json"
    if not path.exists():
        raise HTTPException(404, "Análisis no encontrado")
    result = load_json(path)
    manifest, folder = published()
    if manifest["id"] != result["dataset_id"] or result.get("analysis_version") != ANALYSIS_VERSION:
        raise HTTPException(409, "El dataset cambió; vuelve a generar el análisis")
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
        raise HTTPException(422, "El límite debe estar entre 1 y 10000")
    result, folder = existing(identifier)
    selection = HarmonizedSelection(**result["selection"])
    with selection_database(selection, folder) as (connection, _):
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
            readme = "NINA · Actividad armonizada\n\n" + "\n".join(result["limitations"])
            readme += "\n\nEstado de validación: " + result["validation_status"]
            readme += "\n\nUnidad: " + UNIT + "\nVersión: " + result["dataset_id"]
            readme += "\n\n" + result["legal"] + "\n" + "\n".join(result["references"])
            readme += (
                "\n\nLas celdas de cells.csv corresponden al mes seleccionado. "
                "Las filas diarias tienen sesgo de muestreo; no calcular anomalías diarias.\n"
            )
            archive.writestr("LEEME.md", readme)
            selection = HarmonizedSelection(**result["selection"])
            with selection_database(selection, folder) as (connection, _):
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


@router.post("/api/harmonized/assistant", response_model=AssistantResponse)
def assistant(question: HarmonizedQuestion):
    result, _ = existing(question.analysis_id)
    selected = result["selected"]
    value = selected["value"]
    answer = f"El período {selected['year']}-{selected['month']:02d} tiene " + (
        f"{value:,.2f} unidades de actividad equivalente VIIRS."
        if value is not None
        else f"cobertura insuficiente para un valor comparable ({selected['status']})."
    )
    if selected["historical_median"] is not None:
        answer += (
            f" La mediana del mismo mes en {selected['historical_n']} años anteriores es "
            f"{selected['historical_median']:,.2f}; "
            f"diferencia {selected['anomaly_percent']:+.1f} %."
        )
    else:
        answer += " No hay una comparación histórica elegible de al menos cinco años para este mes."
    text = question.question.lower()
    if any(term in text for term in ["cobertura", "nube", "calidad", "fiable"]):
        answer = (
            f"El estado del mes es {selected['status']}. Hay soporte válido en "
            f"{selected['valid_region_days']} de {selected['expected_region_days']} "
            "combinaciones región/día. Este soporte describe el archivo disponible; "
            "no reconstruye nubes ni todas las oportunidades de observación locales."
        )
    elif any(term in text for term in ["sensor", "modis", "viirs", "armoniz"]):
        answer = (
            "La unidad es una celda geográfica activa por día, llevada a una escala "
            "equivalente a VIIRS. MODIS se ajusta con años de solapamiento reservados "
            "para validar; el origen y los ajustes quedan en la exportación. "
            "Una unidad ajustada no representa un nuevo punto de fuego observado."
        )
    elif any(term in text for term in ["evac", "mañana", "predic", "causa", "propaga"]):
        answer = (
            "Este análisis aporta contexto de actividad detectada. No contiene un modelo "
            "de propagación, causalidad ni predicción que permita responder esa pregunta."
        )
    if selected["partial_coverage"]:
        answer += " El archivo es parcial: la cifra disponible no certifica el total del ámbito solicitado."
    answer += (
        " Estos valores describen actividad detectada; no estiman incendios individuales, "
        "área quemada ni propagación."
    )
    if not result["scientifically_validated"]:
        answer = "Resultado experimental. " + answer
    return {
        "answer": answer,
        "analysis_id": result["id"],
        "dataset_id": result["dataset_id"],
        "facts": selected,
        "references": result["references"],
        "mode": "deterministic_grounded",
        "external_llm_used": False,
    }
