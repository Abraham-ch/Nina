"""Producto común versionado; ninguna puerta fallida se publica en la aplicación."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import h3
import pandas as pd

from nina.calibration import Coefficient, select_coefficient
from nina.io.harmonization import connect, file_digest, log, read_json, sql_literal, write_json

COUNTRY_NAMES = {"United_States": "United States of America"}
# Relleno de la referencia (AGENTS.md §10.4, ADR 0005): un día de la era S-NPP usa NOAA-20 con
# su puente cuando S-NPP no es válido o registra menos del 40 % de las celdas que NOAA-20 vio
# ese mismo día en el mismo país (apagón parcial), siempre que NOAA-20 tenga ≥ 50 celdas.
PARTIAL_OUTAGE_RATIO = 0.40
PARTIAL_OUTAGE_MIN_CELLS = 50
# Terra sola (nov-2000 → jul-2002) tiene errores anuales de ±40 % fuera de muestra: no se sirve.
SERVED_SAMPLINGS = {"terra_aqua", "noaa20"}
SOURCE_PLATFORMS = {
    "modis": ["Terra", "Aqua"],
    "viirs-snpp": ["S-NPP"],
    "viirs-jpss1": ["NOAA-20"],
    "viirs-jpss2": ["NOAA-21"],
}


def archive_windows(workspace: Path, prepared: dict[str, Any]) -> list[dict[str, Any]]:
    """Distingue años de archivo declarados de extremos meramente observados."""
    windows = []
    life = {
        "Terra": "terra",
        "Aqua": "aqua",
        "S-NPP": "snpp",
        "NOAA-20": "noaa20",
        "NOAA-21": "noaa21",
    }
    for entry in read_json(workspace / "source/history-inputs.json")["files"]:
        country = COUNTRY_NAMES.get(entry["country"], entry["country"])
        for platform in SOURCE_PLATFORMS[entry["source"]]:
            lifecycle = prepared["sensor_lifecycle"][life[platform]]
            first = max(f"{entry['year']}-01-01", str(lifecycle["first_date"]))
            last = min(f"{entry['year']}-12-31", str(lifecycle.get("last_date") or "9999-12-31"))
            if first <= last:
                windows.append(
                    {
                        "country": country,
                        "platform": platform,
                        "first_date": first,
                        "last_date": last,
                        "processing": "SP",
                        "basis": "annual_archive",
                    }
                )
    countries = read_json(workspace / "web/public/assets/countries.geojson")["features"]
    country_names = [f["properties"]["name"] for f in countries] + ["unassigned"]
    for entry in read_json(workspace / "data/global-import.json")["files"]:
        if entry.get("spatial_scope") != "world":
            continue
        for platform in SOURCE_PLATFORMS[entry["source"]]:
            for country in country_names:
                windows.append(
                    {
                        "country": country,
                        "platform": platform,
                        "first_date": entry["first_date"],
                        "last_date": entry["last_date"],
                        "processing": entry["processing"],
                        "basis": entry["coverage_basis"],
                    }
                )
    windows.extend(observed_windows(workspace, prepared, country_names))
    return windows


def observed_windows(
    workspace: Path, prepared: dict[str, Any], country_names: list[str]
) -> list[dict[str, Any]]:
    """Agrega las ventanas declaradas de los lotes del MVP observado."""
    windows = []
    observed = workspace / "source/interim/observed_batch_coverage.json"
    if observed.exists():
        metadata = read_json(observed)
        if metadata["parquet_sha256"] != prepared["input_reports"][0]["sha256"]:
            raise ValueError("El ámbito observado corresponde a otro Parquet")
        for entry in metadata["batches"]:
            if not entry.get("coverage_start") or not entry.get("coverage_end"):
                continue
            if entry["spatial_scope"] not in {"world", "PER"}:
                continue
            areas = country_names if entry["spatial_scope"] == "world" else ["Peru"]
            for platform in SOURCE_PLATFORMS[entry["source"]]:
                for country in areas:
                    windows.append(
                        {
                            "country": country,
                            "platform": platform,
                            "first_date": entry["coverage_start"],
                            "last_date": entry["coverage_end"],
                            "processing": entry["processing"],
                            "basis": "annual_archive"
                            if entry["coverage_basis"] == "provider_annual_file"
                            else entry["coverage_basis"],
                        }
                    )
    return windows


def build_support(connection: Any, workspace: Path, prepared: dict[str, Any]) -> None:
    """Soporte del archivo y régimen elegido, independiente de sus focos locales."""
    frame = pd.DataFrame.from_records(archive_windows(workspace, prepared))
    connection.register("window_frame", frame)
    connection.execute("CREATE OR REPLACE TABLE archive_windows AS SELECT * FROM window_frame")
    connection.unregister("window_frame")
    snpp = prepared["sensor_lifecycle"]["snpp"]
    aqua = prepared["sensor_lifecycle"]["aqua"]
    noaa20 = prepared["sensor_lifecycle"]["noaa20"]
    snpp_first, snpp_last = sql_literal(snpp["first_date"]), sql_literal(snpp["last_date"])
    connection.execute("""CREATE OR REPLACE TABLE archive_days AS
        SELECT country,platform,day::DATE AS day,
            CASE WHEN bool_or(processing='SP') THEN 'SP' ELSE 'NRT' END AS processing,
            bool_or(basis='annual_archive') AS declared_archive
        FROM archive_windows,LATERAL generate_series(first_date::DATE,last_date::DATE,
            INTERVAL 1 DAY) d(day) GROUP BY ALL""")
    official_ok = """NOT EXISTS(SELECT 1 FROM official_missing_dates o
                WHERE {a}.country IN ('United States of America','Canada') AND o.day::DATE={a}.day
                AND o.quality={a}.processing AND (o.satellite LIKE {p}||' (%'
                    OR ({p}='S-NPP' AND o.satellite='Suomi NPP (VIIRS)')))"""
    fill = f"""coalesce(v.n20_ok,false) AND (NOT coalesce(v.snpp_ok,false) OR (
            coalesce(c.n20_cells,0)>={PARTIAL_OUTAGE_MIN_CELLS}
            AND coalesce(c.snpp_cells,0)<{PARTIAL_OUTAGE_RATIO}*c.n20_cells))"""
    connection.execute(f"""CREATE OR REPLACE TABLE support AS WITH dates AS (
        SELECT DISTINCT country,day FROM archive_days
    ),viirs AS (SELECT a.country,a.day,
        coalesce(bool_or(coalesce(q.valid,false) AND {official_ok.format(a="a", p="a.platform")})
            FILTER(WHERE a.platform='S-NPP'),false) AS snpp_ok,
        coalesce(bool_or(coalesce(q.valid,false) AND {official_ok.format(a="a", p="a.platform")})
            FILTER(WHERE a.platform='NOAA-20'),false) AS n20_ok
        FROM archive_days a LEFT JOIN quality q ON q.platform=a.platform AND q.day=a.day
        WHERE a.platform IN ('S-NPP','NOAA-20')
        AND a.day BETWEEN {snpp_first}::DATE AND {snpp_last}::DATE GROUP BY ALL
    ),viirs_cells AS (SELECT country,day,
        count(*) FILTER(WHERE platform='S-NPP') AS snpp_cells,
        count(*) FILTER(WHERE platform='NOAA-20') AS n20_cells
        FROM activity WHERE platform IN ('S-NPP','NOAA-20')
        AND day BETWEEN {sql_literal(noaa20["first_date"])}::DATE AND {snpp_last}::DATE
        GROUP BY ALL
    ),chosen AS (SELECT d.country,d.day,CASE WHEN d.day<{snpp_first}::DATE
        THEN CASE WHEN d.day<{sql_literal(aqua["first_date"])}::DATE
            THEN 'terra_only' ELSE 'terra_aqua' END
        WHEN d.day<={snpp_last}::DATE THEN CASE WHEN {fill} THEN 'noaa20' ELSE 'reference' END
        ELSE 'noaa20' END AS sampling,
        d.day BETWEEN {snpp_first}::DATE AND {snpp_last}::DATE AND {fill} AS snpp_filled
        FROM dates d LEFT JOIN viirs v USING(country,day) LEFT JOIN viirs_cells c USING(country,day)
    ),required AS (SELECT c.*,p.platform FROM chosen c CROSS JOIN (VALUES
        ('Terra'),('Aqua'),('S-NPP'),('NOAA-20')) p(platform)
        WHERE (sampling='terra_only' AND p.platform='Terra')
        OR (sampling='terra_aqua' AND p.platform IN ('Terra','Aqua'))
        OR (sampling='reference' AND p.platform='S-NPP')
        OR (sampling='noaa20' AND p.platform='NOAA-20')
    ) SELECT r.country,r.day,r.sampling,count(*) AS required_platforms,
        count(a.platform) AS archive_platforms,
        count(*) FILTER(WHERE a.platform IS NOT NULL AND coalesce(q.valid,false)
            AND NOT EXISTS(SELECT 1 FROM official_missing_dates o
                WHERE r.country IN ('United States of America','Canada') AND o.day::DATE=r.day
                AND o.quality=a.processing AND (o.satellite LIKE r.platform||' (%'
                    OR (r.platform='S-NPP' AND o.satellite='Suomi NPP (VIIRS)'))))
            AS valid_platforms,
        coalesce(bool_and(a.declared_archive),false) AS declared_archive,
        coalesce(bool_or(a.processing<>'SP'),false) AS is_provisional,
        r.day={snpp_last}::DATE AS transition_day,
        coalesce(r.snpp_filled,false) AS snpp_filled
        FROM required r LEFT JOIN archive_days a USING(country,day,platform)
        LEFT JOIN quality q ON q.platform=r.platform AND q.day=r.day GROUP BY ALL""")


def coefficient_choices(connection: Any, model: dict[str, Any]) -> None:
    """Los estratos que fallan se abstienen; el fallback queda en cada celda."""
    coefficients = [Coefficient(**c) for c in model["coefficients"]]
    validated = {
        (s["country"], int(s["biome"]), sampling): bool(s["passed"])
        for sampling, validation in model["validation"].items()
        for s in validation["strata"]
    }
    choices = []
    for country, biome in connection.execute(
        "SELECT DISTINCT country,biome FROM grid_cells"
    ).fetchall():
        for month in range(1, 13):
            for sampling in ["terra_only", "terra_aqua", "noaa20"]:
                coefficient = select_coefficient(
                    coefficients, str(country), int(biome), month, sampling
                )
                if coefficient:
                    choices.append(
                        {
                            "country": country,
                            "biome": biome,
                            "month": month,
                            "sampling": sampling,
                            "coefficient": coefficient.coefficient,
                            "fallback_level": coefficient.fallback_level,
                            "validated": sampling in SERVED_SAMPLINGS
                            and validated.get((country, biome, sampling), False),
                        }
                    )
    connection.register("choice_frame", pd.DataFrame.from_records(choices))
    connection.execute("CREATE OR REPLACE TABLE coefficient_choices AS SELECT * FROM choice_frame")
    connection.unregister("choice_frame")


def write_tables(connection: Any, destination: Path) -> dict[str, str]:
    """Orden y compresión estables: el mismo producto conserva los mismos hashes."""
    hashes = {}
    connection.execute("SET threads=1")
    for table, order in [
        ("harmonized_cell_day", "cell,day"),
        ("support", "country,day"),
        ("grid_cells", "cell"),
    ]:
        path = destination / f"{table}.parquet"
        connection.execute(
            f"COPY (SELECT * FROM {table} ORDER BY {order}) TO {sql_literal(path)} "
            "(FORMAT PARQUET,COMPRESSION ZSTD)"
        )
        hashes[path.name] = file_digest(path)
    return hashes


def assemble(connection: Any, destination: Path, model: dict[str, Any]) -> dict[str, str]:
    """Combina la referencia y los ajustes sin multiplicar puntos originales."""
    coefficient_choices(connection, model)
    connection.execute("""CREATE OR REPLACE TABLE harmonized_cell_day AS
        WITH selected AS (SELECT a.cell,a.day,a.country,a.biome,s.sampling,
            bool_or(a.processing<>'SP') AS is_provisional,
            string_agg(DISTINCT a.platform, '+' ORDER BY a.platform) AS source_mix,
            sum(a.pixel_rows) AS pixel_rows
            FROM activity a JOIN support s USING(country,day)
            WHERE s.valid_platforms=s.required_platforms AND NOT s.transition_day
            AND ((s.sampling='reference' AND a.platform='S-NPP')
                OR (s.sampling='terra_only' AND a.platform='Terra')
                OR (s.sampling='terra_aqua' AND a.platform IN ('Terra','Aqua'))
                OR (s.sampling='noaa20' AND a.platform='NOAA-20')) GROUP BY ALL
        ) SELECT s.*,1 AS observed_active_cell_day,
            CASE WHEN s.sampling='reference' THEN 1.0
                WHEN c.validated THEN c.coefficient ELSE NULL END AS active_harmonized,
            CASE WHEN s.sampling='reference' THEN 'reference' ELSE c.fallback_level END
                AS coefficient_fallback,
            s.sampling='reference' OR coalesce(c.validated,false) AS calibration_validated,
            false AS data_gap,false AS partial_coverage
        FROM selected s LEFT JOIN coefficient_choices c ON c.country=s.country
            AND c.biome=s.biome AND c.month=month(s.day) AND c.sampling=s.sampling""")
    connection.create_function("grid_latitude", grid_latitude)
    connection.create_function("grid_longitude", grid_longitude)
    connection.execute("""CREATE OR REPLACE TABLE grid_cells AS
        SELECT cell,country,biome,grid_latitude(cell) AS latitude,
            grid_longitude(cell) AS longitude FROM grid_cells""").fetchall()
    connection.remove_function("grid_latitude")
    connection.remove_function("grid_longitude")
    return write_tables(connection, destination)


def grid_latitude(cell: str) -> float:
    return float(h3.cell_to_latlng(cell)[0])


def grid_longitude(cell: str) -> float:
    return float(h3.cell_to_latlng(cell)[1])


def version_registry(
    connection: Any, destination: Path, manifest: dict[str, Any], model: dict[str, Any]
) -> None:
    """Registro consultable de versión y evidencia, sin dependencias de PostGIS."""
    record = {
        "nina_version": model["method_version"],
        "id": model["id"],
        "created_at": manifest["created_at"],
        "input_revision": model["input_revision"],
        "configuration_hash": manifest["configuration_hash"],
        "metrics": json.dumps(manifest["validation"]),
        "auxiliary_versions": json.dumps(manifest["auxiliaries"]),
    }
    connection.register("version_frame", pd.DataFrame([record]))
    connection.execute("CREATE OR REPLACE TABLE dataset_versions AS SELECT * FROM version_frame")
    connection.unregister("version_frame")
    path = destination / "dataset_versions.parquet"
    connection.execute(f"COPY dataset_versions TO {sql_literal(path)} (FORMAT PARQUET)")
    manifest["hashes"][path.name] = file_digest(path)


def publish(workspace: Path) -> dict[str, Any]:
    """Publica solo si la evaluación y el reporte de aceptación están aprobados."""
    folder = workspace / "source/interim/harmonization"
    model = read_json(folder / "model.json")
    acceptance_file = workspace / "source/reports" / f"acceptance_{model['id']}.json"
    if not model["publishable"] or not acceptance_file.exists():
        raise ValueError(
            "Publicación bloqueada: puertas científicas o evidencia de aceptación incompletas"
        )
    acceptance = read_json(acceptance_file)
    if acceptance.get("input_revision") != model["input_revision"] or not acceptance.get(
        "publishable"
    ):
        raise ValueError("El reporte de aceptación no aprueba estas entradas")
    return build_artifact(workspace, model, workspace / "source/harmonized", "published")


def stage_review(workspace: Path) -> dict[str, Any]:
    """Construye un borrador local; no habilita su consulta ni altera las puertas."""
    model = read_json(workspace / "source/interim/harmonization/model.json")
    return build_artifact(workspace, model, workspace / "source/review", "experimental_candidate")


def build_artifact(
    workspace: Path, model: dict[str, Any], artifact_root: Path, status: str
) -> dict[str, Any]:
    """Artefacto inmutable, con procedencia y estado explícito de validación."""
    folder = workspace / "source/interim/harmonization"
    destination = artifact_root / model["id"]
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "manifest.json").exists():
        previous = cast(dict[str, Any], read_json(destination / "manifest.json"))
        if any(
            file_digest(destination / name) != digest for name, digest in previous["hashes"].items()
        ):
            raise ValueError("La versión publicada se modificó; no se sobrescribe")
        write_json(destination.parent / "current.json", previous)
        return previous
    connection = connect(folder / "candidate.duckdb")
    try:
        prepared = read_json(folder / "prepared.json")
        if model["configuration"]["input_mask_method_version"] != prepared["method_version"]:
            raise ValueError("Cambió el filtro después del entrenamiento; vuelve a entrenar")
        build_support(connection, workspace, prepared)
        hashes = assemble(connection, destination, model)
        firms_legal = read_json(workspace / "docs/reference/firms_legal.json")["en"]
        manifest = {
            "id": model["id"],
            "status": status,
            "scientifically_validated": status == "published",
            "method_version": model["method_version"],
            "created_at": datetime.now(UTC).isoformat(),
            "published_at": datetime.now(UTC).isoformat() if status == "published" else None,
            "as_of_date": str(
                connection.execute("SELECT max(day) FROM normalized").fetchall()[0][0]
            ),
            "hashes": hashes,
            "input_revision": model["input_revision"],
            "configuration_hash": hashlib.sha256(
                json.dumps(model["configuration"], sort_keys=True).encode()
            ).hexdigest(),
            "validation": {
                key: {k: v for k, v in validation.items() if k != "predictions"}
                for key, validation in model["validation"].items()
            },
            "geographic_diagnostic": {
                key: {k: v for k, v in diagnostic.items() if k != "predictions"}
                for key, diagnostic in model["geographic_diagnostic"].items()
            },
            "input_mask_method_version": model["configuration"]["input_mask_method_version"],
            "gates": model["gates"],
            "unit": model["unit"],
            "local_cloud_opportunities": "not_reconstructed",
            "references": [
                "https://firms.modaps.eosdis.nasa.gov/download/",
                "https://doi.org/10.5067/FIRMS/MODIS/MCD14DL.NRT.0061",
                "https://doi.org/10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002",
            ],
            "legal": firms_legal["citation"]
            + " "
            + firms_legal["warning"]
            + " NASA does not endorse NINA.",
            "h3_resolution": model["configuration"]["h3_resolution"],
            "auxiliaries": [
                {k: v for k, v in item.items() if k != "path"} for item in prepared["auxiliaries"]
            ],
            "inputs": [
                {key: item[key] for key in ["filename", "sha256", "rows_read", "accepted"]}
                for item in prepared["input_reports"]
            ],
            "synthetic": False,
        }
        version_registry(connection, destination, manifest, model)
        write_json(destination / "manifest.json", manifest)
        pointer = destination.parent / "current.json"
        temporary = pointer.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        temporary.replace(pointer)
        log(status, id=model["id"], hashes=hashes)
        return manifest
    finally:
        connection.close()


def main() -> None:
    """CLI explícita de publicación; nunca se ejecuta al iniciar la web."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--review", action="store_true")
    args = parser.parse_args()
    if args.review:
        stage_review(args.workspace.resolve())
    else:
        publish(args.workspace.resolve())


if __name__ == "__main__":
    main()
