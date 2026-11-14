"""Construcción auditable del candidato H3 a partir de archivos NASA identificados."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import duckdb
import h3
import yaml

from nina.calibration import METHOD_VERSION
from nina.config import (
    H3_RES,
    KEEP_TYPES,
    MIN_CONFIDENCE_CLASS,
    SERIES_START_DATE,
    STATIC_SOURCE_H3_RES,
    STATIC_SOURCE_MIN_DAYS_PER_YEAR,
    VOLCANO_BUFFER_KM,
)
from nina.io.geography import cell_geography
from nina.io.static_sources import build_catalog

MAX_SCHEMA_ERROR_FRACTION = 0.01
MAX_VEGETATION_REMOVAL = 0.02
MIN_STATIC_RECALL = 0.8


def read_json(path: Path) -> Any:
    """Lee un artefacto UTF-8 local."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    """Escribe JSON legible, sin serializar valores no finitos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def sql_literal(value: object) -> str:
    """Escapa un literal para los nombres de archivo de COPY/read_parquet."""
    return "'" + str(value).replace("'", "''") + "'"


def log(event: str, **values: Any) -> None:
    """Progreso estructurado sin credenciales ni URLs autenticadas."""
    print(json.dumps({"event": event, **values}, ensure_ascii=False, default=str), flush=True)


def file_digest(path: Path) -> str:
    """Hash por bloques, también para archivos mundiales grandes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    """Conexión de construcción separada del servidor, con memoria acotada."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    connection.execute("SET memory_limit=?", [os.getenv("NINA_BUILD_MEMORY_LIMIT", "2GB")])
    connection.execute("SET threads=2")
    connection.execute("SET preserve_insertion_order=false")
    return connection


def scalar_int(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    """Consulta escalar cuyo resultado nunca puede faltar."""
    rows = connection.execute(query).fetchall()
    assert len(rows) == 1
    return int(rows[0][0])


def h3_index(latitude: float, longitude: float) -> str:
    """Celda de control de persistencia; la agregación principal usa su padre 7."""
    return str(h3.latlng_to_cell(latitude, longitude, STATIC_SOURCE_H3_RES))


def normalize_input(
    connection: duckdb.DuckDBPyConnection,
    entry: dict[str, Any],
    cache: Path,
) -> dict[str, Any]:
    """Normaliza sin eliminar confianza baja ni tipos: su descarte se audita después."""
    path = Path(entry["path"])
    digest = entry["sha256"]
    suffix = f"|h3-{STATIC_SOURCE_H3_RES}-pixel-v3"
    if MIN_CONFIDENCE_CLASS != "nominal" or str(SERIES_START_DATE) != "2000-11-01":
        suffix += f"|{MIN_CONFIDENCE_CLASS}|{SERIES_START_DATE}"
    identifier = hashlib.sha256((str(digest) + suffix).encode()).hexdigest()[:24]
    parquet = cache / f"{identifier}.parquet"
    report_path = cache / f"{identifier}.json"
    if parquet.exists() and report_path.exists():
        return cast(dict[str, Any], read_json(report_path))
    log("normalizing", file=path.name)
    if path.suffix == ".parquet":
        reader = f"read_parquet({sql_literal(path)})"
        query = f"""SELECT id AS pixel_id,latitude,longitude,acquired,platform,processing,fire_type,
            confidence,version,frp,scan*track AS pixel_area_km2 FROM {reader}"""
    else:
        source = str(entry["source"])
        platform = (
            "CASE lower(trim(satellite)) WHEN 'a' THEN 'Aqua' WHEN 'aqua' THEN 'Aqua' "
            "WHEN 't' THEN 'Terra' WHEN 'terra' THEN 'Terra' END"
            if source == "modis"
            else sql_literal(
                {
                    "viirs-snpp": "S-NPP",
                    "viirs-jpss1": "NOAA-20",
                    "viirs-jpss2": "NOAA-21",
                }[source]
            )
        )
        reader = f"read_csv({sql_literal(path)},header=true,all_varchar=true)"
        columns = {
            str(r[0]) for r in connection.execute(f"DESCRIBE SELECT * FROM {reader}").fetchall()
        }
        type_expression = 'try_cast("type" AS INTEGER)' if "type" in columns else "NULL::INTEGER"
        query = f"""SELECT try_cast(latitude AS DOUBLE) AS latitude,
            try_cast(longitude AS DOUBLE) AS longitude,
            try_strptime(acq_date||' '||lpad(trim(acq_time),4,'0'),'%Y-%m-%d %H%M') AS acquired,
            {platform} AS platform,'SP' AS processing,{type_expression} AS fire_type,
            confidence,version,try_cast(frp AS DOUBLE) AS frp,
            try_cast(scan AS DOUBLE)*try_cast(track AS DOUBLE) AS pixel_area_km2 FROM {reader}"""
        query = f"""SELECT substr(sha256({sql_literal(source)}||'|'||platform||'|'||
            strftime(acquired,'%Y-%m-%dT%H:%M:%S')||'|'||printf('%.6f',latitude)||'|'||
            printf('%.6f',longitude)),1,32) AS pixel_id,* FROM ({query})"""
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE input_rows AS SELECT *,
        CASE WHEN latitude IS NULL OR longitude IS NULL OR NOT isfinite(latitude)
            OR NOT isfinite(longitude) OR latitude NOT BETWEEN -90 AND 90
            OR longitude NOT BETWEEN -180 AND 180 THEN 'invalid_coordinates'
        WHEN acquired IS NULL THEN 'invalid_datetime'
        WHEN acquired::DATE<{sql_literal(SERIES_START_DATE)}::DATE THEN 'pre_nov2000_quality'
        WHEN acquired::DATE>current_date THEN 'future_date'
        WHEN platform IS NULL THEN 'unknown_satellite'
        WHEN platform IN ('Aqua','Terra') AND (version LIKE '4%' OR version LIKE '5%')
            THEN 'unsupported_collection'
        WHEN NOT coalesce(CASE WHEN platform IN ('Aqua','Terra') THEN
            try_cast(confidence AS DOUBLE) BETWEEN 0 AND 100
            ELSE lower(confidence) IN ('l','n','h','7','8','9') END,false) THEN 'invalid_confidence'
        WHEN frp IS NOT NULL AND (NOT isfinite(frp) OR frp<0) THEN 'invalid_frp'
        ELSE NULL END AS qa_reason FROM ({query})""")
    reasons = {
        str(k): int(n)
        for k, n in connection.execute(
            "SELECT qa_reason,count(*) FROM input_rows WHERE qa_reason IS NOT NULL GROUP BY 1",
        ).fetchall()
    }
    total = scalar_int(connection, "SELECT count(*) FROM input_rows")
    invalid = sum(n for reason, n in reasons.items() if reason != "pre_nov2000_quality")
    report = {
        "filename": path.name,
        "path": str(path),
        "sha256": digest,
        "rows_read": total,
        "rejected": reasons,
        "parquet": str(parquet),
    }
    if total and invalid / total > MAX_SCHEMA_ERROR_FRACTION:
        write_json(report_path, {**report, "status": "failed_quality_gate"})
        raise ValueError(f"{path.name}: más de 1 % de registros inválidos")
    minimum = {"low": 0, "nominal": 30, "high": 80}[MIN_CONFIDENCE_CLASS]
    excluded = {"low": "()", "nominal": "('l','7')", "high": "('l','7','n','8')"}
    viirs_filter = (
        "false"
        if MIN_CONFIDENCE_CLASS == "low"
        else ("lower(confidence) IN " + excluded[MIN_CONFIDENCE_CLASS])
    )
    connection.execute(f"""COPY (SELECT pixel_id,h3_index(latitude,longitude) AS cell8,
        acquired::DATE AS day,platform,processing,fire_type,
        version,
        CASE WHEN platform IN ('Aqua','Terra') THEN try_cast(confidence AS DOUBLE)<{minimum}
            ELSE {viirs_filter} END AS low_confidence,
        1::BIGINT AS n,coalesce(frp,0) AS frp_sum,
        coalesce(pixel_area_km2,0) AS area_sum,
        CASE WHEN pixel_area_km2>4 THEN 1 ELSE 0 END AS wide_pixels
        FROM input_rows WHERE qa_reason IS NULL)
        TO {sql_literal(parquet)} (FORMAT PARQUET,COMPRESSION ZSTD)""")
    report["accepted"] = total - sum(reasons.values())
    report["status"] = "normalized"
    assert total == int(report["accepted"]) + sum(reasons.values())
    write_json(report_path, report)
    connection.execute("DROP TABLE input_rows")
    return report


def validate_mask(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Mide falsos descartes y recuperación antes de permitir publicar."""
    mask = connection.execute("""SELECT
        sum(n) FILTER(WHERE platform IN ('Aqua','Terra') AND processing='SP' AND fire_type=0),
        sum(n) FILTER(WHERE platform IN ('Aqua','Terra') AND processing='SP' AND fire_type=0
            AND (urban OR water OR volcano OR persistent OR known_static)),
        count(DISTINCT cell8) FILTER(WHERE platform IN ('Aqua','Terra') AND processing='SP'
            AND fire_type IN (1,2)),
        count(DISTINCT cell8) FILTER(WHERE platform IN ('Aqua','Terra') AND processing='SP'
            AND fire_type IN (1,2)
            AND (urban OR water OR volcano OR persistent OR known_static)) FROM classified
        WHERE day BETWEEN (SELECT min(day) FROM normalized
            WHERE platform='S-NPP' AND processing='SP')
            AND (SELECT max(day) FROM normalized
                WHERE platform='S-NPP' AND processing='SP')
        AND day>mask_training_cutoff AND day<=mask_test_end""").fetchone()
    assert mask is not None
    fraction_removed = float(mask[1] or 0) / max(1, float(mask[0] or 0))
    recall = float(mask[3] or 0) / max(1, float(mask[2] or 0))
    mask_validation = {
        "modis_vegetation_rows": int(mask[0] or 0),
        "vegetation_rows_removed": int(mask[1] or 0),
        "reference_static_cells": int(mask[2] or 0),
        "reference_static_cells_recovered": int(mask[3] or 0),
        "vegetation_removal_fraction": fraction_removed,
        "static_recall": recall,
        "max_vegetation_removal": MAX_VEGETATION_REMOVAL,
        "minimum_recall": MIN_STATIC_RECALL,
        "evaluation_scope": "held_out_MODIS_SP_over_standard_SNPP_overlap",
        "persistence_reference": "nominal_high_VIIRS_only_in_overlap",
        "catalog_reference": "prior_MODIS_labels_excluding_evaluation_period",
        "passed": fraction_removed <= MAX_VEGETATION_REMOVAL and recall >= MIN_STATIC_RECALL,
    }
    return mask_validation


def consolidate(
    connection: duckdb.DuckDBPyConnection, reports: list[dict[str, Any]], folder: Path | None = None
) -> int:
    """Deduplicación determinista por identidad física; devuelve el descarte."""
    signature = (
        hashlib.sha256(
            json.dumps(
                sorted((r["sha256"], Path(r["parquet"]).name, r["accepted"]) for r in reports)
            ).encode()
        ).hexdigest()
        if folder is not None
        else None
    )
    stage_path = folder / "normalized-stage.json" if folder is not None else None
    if stage_path is not None and stage_path.exists():
        stage = read_json(stage_path)
        if stage["signature"] == signature and stage["rows"] == scalar_int(
            connection, "SELECT count(*) FROM normalized"
        ):
            log("reusing_normalized_stage", rows=stage["rows"])
            return sum(int(r["accepted"]) for r in reports) - int(stage["rows"])
    files = [r["parquet"] for r in reports]
    paths = "[" + ",".join(sql_literal(p) for p in files) + "]"
    current = connection.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name='normalized'"
    ).fetchone()
    if current and current[0] == "VIEW":
        connection.execute("DROP VIEW normalized")
    connection.execute(f"""CREATE OR REPLACE TABLE normalized AS
        SELECT * FROM read_parquet({paths}) QUALIFY row_number() OVER(PARTITION BY pixel_id
            ORDER BY (processing='SP') DESC,version DESC,low_confidence ASC,
                fire_type NULLS LAST,frp_sum DESC,area_sum ASC)=1""")
    unique_rows = scalar_int(connection, "SELECT count(*) FROM normalized")
    connection.execute("CHECKPOINT").fetchall()
    if stage_path is not None:
        write_json(stage_path, {"signature": signature, "rows": unique_rows})
    return sum(int(r["accepted"]) for r in reports) - unique_rows


def filter_configuration() -> dict[str, Any]:
    """Parámetros efectivos que determinan los filtros y sus cachés."""
    return {
        "h3_resolution": H3_RES,
        "static_resolution": STATIC_SOURCE_H3_RES,
        "static_min_days": STATIC_SOURCE_MIN_DAYS_PER_YEAR,
        "min_confidence": MIN_CONFIDENCE_CLASS,
        "keep_types": KEEP_TYPES,
        "series_start_date": str(SERIES_START_DATE),
        "volcano_buffer_km": VOLCANO_BUFFER_KM,
    }


def verified_stage(
    connection: duckdb.DuckDBPyConnection,
    folder: Path,
    reports: list[dict[str, Any]],
    *,
    refresh: bool,
) -> int:
    """Reutiliza únicamente una etapa cuya contabilidad coincide con sus insumos."""
    if not refresh:
        return consolidate(connection, reports, folder)
    previous = read_json(folder / "prepared.json")
    expected = sum(int(r["accepted"]) for r in reports)
    duplicates = int(previous["cross_input_duplicates"])
    if scalar_int(connection, "SELECT count(*) FROM normalized") != expected - duplicates or (
        previous["input_reports"] != reports
    ):
        raise ValueError("El caché cambió; reconstruye sin --refresh-derived")
    if previous.get("filter_configuration") != filter_configuration():
        raise ValueError("Cambió la configuración; reconstruye sin --refresh-derived")
    return duplicates


def reconcile_activity(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """El estándar regional solo reemplaza NRT dentro de ese mismo país."""
    condition = """EXISTS(SELECT 1 FROM region_daily_counts s WHERE s.platform=n.platform
        AND s.day=n.day AND s.country=n.country AND s.processing='SP') OR EXISTS(
        SELECT 1 FROM global_standard_windows w WHERE w.platform=n.platform
        AND n.day BETWEEN w.first_date AND w.last_date)"""
    result = connection.execute(
        "SELECT count(*),coalesce(sum(pixel_rows),0) FROM activity n "
        "WHERE processing<>'SP' AND (" + condition + ")"
    ).fetchall()[0]
    connection.execute("DELETE FROM activity n WHERE processing<>'SP' AND (" + condition + ")")
    return {"cell_days": int(result[0]), "pixel_rows": int(result[1])}


def source_windows(connection: duckdb.DuckDBPyConnection, workspace: Path) -> None:
    """Usa el ámbito documentado del archivo, sin inferir cobertura de un punto."""
    connection.execute("""CREATE OR REPLACE TABLE global_standard_windows(
        platform VARCHAR,first_date DATE,last_date DATE)""")
    path = workspace / "data/global-import.json"
    mapping = {
        "modis": ["Terra", "Aqua"],
        "viirs-snpp": ["S-NPP"],
        "viirs-jpss1": ["NOAA-20"],
        "viirs-jpss2": ["NOAA-21"],
    }
    windows: list[tuple[str, str, str]] = []
    if path.exists():
        for item in read_json(path)["files"]:
            if item.get("processing") == "SP" and item.get("spatial_scope") == "world":
                windows.extend(
                    (platform, item["first_date"], item["last_date"])
                    for platform in mapping[item["source"]]
                )
    if windows:
        connection.executemany("INSERT INTO global_standard_windows VALUES (?,?,?)", windows)
    connection.execute("""CREATE OR REPLACE TABLE region_daily_counts AS
        SELECT country,platform,day,processing,sum(n) n FROM classified GROUP BY ALL""")


def classify_rows(
    connection: duckdb.DuckDBPyConnection, *, reuse_persistence: bool = False
) -> dict[str, Any]:
    """Filtros trazables con persistencia por año y celda, antes de agregar."""
    if not reuse_persistence:
        connection.execute(f"""CREATE OR REPLACE TABLE persistence AS
        SELECT cell8,year(day) AS year,count(DISTINCT day) AS days
        FROM normalized WHERE NOT low_confidence AND (
            platform NOT IN ('Terra','Aqua') OR day<coalesce(
                (SELECT min(day) FROM normalized WHERE platform='S-NPP' AND processing='SP'),
                DATE '9999-12-31')) GROUP BY 1,2
            HAVING count(DISTINCT day)>={STATIC_SOURCE_MIN_DAYS_PER_YEAR}""")
    catalog = build_catalog(connection)
    keep_types = "(" + ",".join(str(t) for t in KEEP_TYPES) + ")"
    connection.execute(f"""CREATE OR REPLACE VIEW classified AS SELECT n.*,c.cell,c.country,
        c.biome,c.ecoregion,c.latitude,c.longitude,c.urban,c.water,c.volcano,
        p.cell8 IS NOT NULL AS persistent,
        s.cell8 IS NOT NULL AS known_static,
        coalesce(k.train_cutoff,w.train_cutoff) AS mask_training_cutoff,
        coalesce(k.test_end,w.test_end) AS mask_test_end,
        CASE WHEN low_confidence THEN 'low_confidence'
            WHEN fire_type IS NOT NULL AND fire_type NOT IN {keep_types}
            THEN 'non_vegetation_type'
            WHEN c.urban OR c.water OR c.volcano OR p.cell8 IS NOT NULL OR s.cell8 IS NOT NULL
                THEN 'static_source_mask'
            ELSE NULL END AS qa_reason
        FROM normalized n JOIN cells c USING(cell8)
        LEFT JOIN persistence p ON p.cell8=n.cell8 AND p.year=year(n.day)
        LEFT JOIN static_catalog s ON s.cell8=n.cell8
        LEFT JOIN mask_cutoffs k ON k.country=c.country
        CROSS JOIN (SELECT train_cutoff,test_end FROM mask_cutoffs WHERE country='world') w""")
    return catalog


def prepare(workspace: Path, *, refresh_derived: bool = False) -> dict[str, Any]:
    """Construye insumos comparables; no publica un dataset armonizado."""
    source = workspace / "source"
    folder = source / "interim/harmonization"
    cache = folder / "inputs"
    cache.mkdir(parents=True, exist_ok=True)
    reports = source / "reports"
    reports.mkdir(exist_ok=True)
    history = read_json(source / "history-inputs.json")
    if history["status"] != "complete":
        raise ValueError("El histórico seleccionado debe estar completamente descargado")
    base = workspace / "data/processed/observations.parquet"
    entries = [
        {"path": str(base), "sha256": file_digest(base), "filename": base.name},
        *history["files"],
    ]
    connection = connect(folder / "candidate.duckdb")
    connection.create_function("h3_index", h3_index)
    try:
        input_reports = [normalize_input(connection, e, cache) for e in entries]
        cross_file_duplicates = verified_stage(
            connection, folder, input_reports, refresh=refresh_derived
        )
        cell_geography(connection, workspace, folder)
        catalog_metadata = classify_rows(connection, reuse_persistence=refresh_derived)
        mask_validation = validate_mask(connection)
        write_json(reports / f"static_mask_validation_{METHOD_VERSION}.json", mask_validation)
        rejection_counts = {
            str(k): int(n)
            for k, n in connection.execute(
                "SELECT qa_reason,sum(n) FROM classified GROUP BY 1",
            ).fetchall()
        }
        log("mask_validation", **mask_validation)
        connection.execute("""CREATE OR REPLACE TABLE global_daily_counts AS
            SELECT platform,day,processing,sum(n) AS n FROM normalized GROUP BY ALL""")
        connection.execute("""CREATE OR REPLACE TABLE grid_cells AS
            SELECT cell,min(country) AS country,min(biome) AS biome FROM cells GROUP BY cell""")
        connection.execute("""CREATE OR REPLACE TABLE activity AS
            SELECT cell,day,platform,processing,g.country,g.biome,
                count(DISTINCT cell8) AS active_subcells,
                sum(n) AS pixel_rows,sum(frp_sum) AS frp_sum,sum(area_sum) AS area_sum,
                sum(wide_pixels) AS wide_pixels
            FROM classified JOIN grid_cells g USING(cell) WHERE qa_reason IS NULL
            GROUP BY cell,day,platform,processing,g.country,g.biome""")
        source_windows(connection, workspace)
        superseded = reconcile_activity(connection)
        rejection_counts["superseded_by_standard"] = superseded["pixel_rows"]
        rejection_counts["None"] -= superseded["pixel_rows"]
        for table in ["activity", "global_daily_counts", "persistence", "static_catalog"]:
            destination = folder / f"{table}.parquet"
            if destination.exists():
                destination.unlink()
            connection.execute(
                f"COPY {table} TO {sql_literal(destination)} (FORMAT PARQUET,COMPRESSION ZSTD)"
            )
        registry = {
            "method_version": METHOD_VERSION,
            "static_catalog": catalog_metadata,
            "filter_configuration": filter_configuration(),
            "created_at": datetime.now(UTC).isoformat(),
            "input_reports": input_reports,
            "input_revision": hashlib.sha256(
                json.dumps(
                    sorted(str(e["sha256"]) for e in entries),
                ).encode()
            ).hexdigest(),
            "auxiliaries": read_json(source / "auxiliary-inputs.json"),
            "known_gaps": yaml.safe_load(
                (workspace / "docs/reference/known_gaps.yaml").read_text(encoding="utf-8")
            ),
            "sensor_lifecycle": yaml.safe_load(
                (workspace / "docs/reference/sensor_lifecycle.yaml").read_text(encoding="utf-8")
            ),
            "qa_reasons": rejection_counts,
            "cross_input_duplicates": cross_file_duplicates,
            "superseded_cell_days": superseded["cell_days"],
            "superseded_pixel_rows": superseded["pixel_rows"],
            "mask_validation": mask_validation,
            "activity_rows": scalar_int(connection, "SELECT count(*) FROM activity"),
            "cell_count": scalar_int(connection, "SELECT count(*) FROM cells"),
            "observation_support": "global_recent_and_multicontinent_historical_activity_proxy",
            "local_cloud_opportunities": "not_reconstructed",
            "status": "candidate_not_published",
        }
        write_json(folder / "prepared.json", registry)
        write_json(reports / f"qa_{METHOD_VERSION}.json", registry)
        write_json(
            source / "sources.yaml",
            {
                "sources": registry["auxiliaries"],
                "history_manifest": "source/history-inputs.json",
                "base_archive": str(base),
            },
        )
        connection.execute("CHECKPOINT")
        log("prepared", activity_rows=registry["activity_rows"], cells=registry["cell_count"])
        return registry
    finally:
        connection.execute("SELECT 1").fetchall()
        connection.remove_function("h3_index")
        connection.close()


def main() -> None:
    """Entrada CLI de construcción, con workspace explícito y artefactos locales."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--refresh-derived", action="store_true")
    args = parser.parse_args()
    prepare(args.workspace.resolve(), refresh_derived=args.refresh_derived)


if __name__ == "__main__":
    main()
