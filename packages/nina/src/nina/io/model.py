"""Entrenamiento, pruebas reservadas y preparación del producto común de actividad."""

from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from nina.calibration import (
    METHOD_VERSION,
    MonthlyPair,
    artifact_id,
    fit_coefficients,
    relative_metrics,
    select_coefficient,
    validate_years,
    apply_noise_ceiling,
    validate_countries,
)
from nina.config import (
    CALIBRATION_COUNTRIES,
    H3_RES,
    MIN_CONFIDENCE_CLASS,
    STATIC_SOURCE_H3_RES,
    STATIC_SOURCE_MIN_DAYS_PER_YEAR,
)
from nina.coverage import daily_quality
from nina.io.catalog import observed_coverage, snapshot_catalog
from nina.io.harmonization import connect, log, read_json, sql_literal, write_json

PLATFORMS = {
    "terra": "Terra",
    "aqua": "Aqua",
    "snpp": "S-NPP",
    "noaa20": "NOAA-20",
    "noaa21": "NOAA-21",
}
HISTORICAL_COUNTRIES = set(CALIBRATION_COUNTRIES)
MIN_TRAINING_YEAR = 2012
RESERVED_TEST_YEAR = 2024
MAX_BAD_DAY_FRACTION = 0.20


def quality_table(connection: Any, prepared: dict[str, Any], catalog: dict[str, Any]) -> None:
    """Soporte diario amplio y huecos oficiales conservados con su ámbito."""
    data = connection.execute("""SELECT platform,day,
        coalesce(sum(n) FILTER(WHERE processing='SP'),sum(n)) AS n,
        coalesce(sum(n) FILTER(WHERE processing='SP'),0)>0 AS standard
        FROM global_daily_counts GROUP BY platform,day ORDER BY platform,day""").fetchall()
    counts: dict[str, dict[date, int]] = defaultdict(dict)
    standard: dict[tuple[str, date], bool] = {}
    for platform, day, n, is_standard in data:
        counts[str(platform)][day] = int(n)
        standard[(str(platform), day)] = bool(is_standard)
    last = max(day for values in counts.values() for day in values)
    records = []
    for key, platform in PLATFORMS.items():
        values = counts.get(platform, {})
        if not values:
            continue
        life = prepared["sensor_lifecycle"][key]
        mission_end = date.fromisoformat(life["last_date"]) if life.get("last_date") else None
        forced: set[date] = set()
        candidates: set[date] = set()
        for item in prepared["known_gaps"]:
            # Los intervalos imprecisos de todo un año no se convierten en un
            # apagón continuo. Los detecta el diagnóstico diario cuando procede.
            if key not in item["satellite"] or (
                item.get("partial") and "FMU" not in item["reason"]
            ):
                continue
            # Solo la falla de hardware documentada (FMU de Aqua) se fuerza; el resto de avisos
            # del Readme se confirma con el conteo diario (ADR 0005).
            target = forced if "FMU" in item["reason"] else candidates
            day = date.fromisoformat(item["start"])
            end = date.fromisoformat(item["end"])
            while day <= end:
                target.add(day)
                day += timedelta(days=1)
        for row in daily_quality(
            values,
            min(values),
            last,
            mission_end=mission_end,
            known_missing=forced,
            known_candidates=candidates,
        ):
            records.append(
                {
                    "platform": platform,
                    "day": row["day"],
                    "n": row["n"],
                    "valid": not row["data_gap"] and row["reason"] != "end_of_mission",
                    "standard": standard.get((platform, row["day"]), False),
                    "reason": row["reason"],
                    "suspicious_day": row["suspicious_day"],
                }
            )
    connection.register("quality_frame", pd.DataFrame.from_records(records))
    connection.execute("CREATE OR REPLACE TABLE quality AS SELECT * FROM quality_frame")
    connection.unregister("quality_frame")
    official = pd.DataFrame.from_records(
        catalog["missing_dates"],
        columns=[
            "day",
            "satellite",
            "quality",
            "scope",
        ],
    )
    connection.register("official_frame", official)
    connection.execute(
        "CREATE OR REPLACE TABLE official_missing_dates AS SELECT * FROM official_frame"
    )
    connection.unregister("official_frame")
    connection.execute("""CREATE OR REPLACE TABLE data_gaps AS
        SELECT platform,day,'broad_activity_proxy' AS scope,reason
        FROM quality WHERE NOT valid AND reason<>'end_of_mission'
        UNION ALL SELECT CASE WHEN satellite='Suomi NPP (VIIRS)' THEN 'S-NPP'
            ELSE split_part(satellite,' (',1) END,day::DATE,scope,'firms_missing_data'
        FROM official_missing_dates""")
    connection.execute("""CREATE OR REPLACE TABLE coverage AS
        SELECT platform,processing,min(day) AS first_date,max(day) AS last_date,
            count(*) AS rows FROM normalized GROUP BY ALL""")


def save_quality(connection: Any, folder: Path) -> dict[str, Any]:
    """Conserva la evidencia temporal, incluyendo avisos sin borrar detecciones."""
    for table in ["quality", "data_gaps", "coverage", "official_missing_dates"]:
        connection.execute(
            f"COPY {table} TO {sql_literal(folder / (table + '.parquet'))} "
            "(FORMAT PARQUET,COMPRESSION ZSTD)"
        )
    connection.execute(f"""COPY (SELECT platform AS satellite_norm,day AS date,n,
        processing AS quality_level FROM global_daily_counts ORDER BY platform,day,processing)
        TO {sql_literal(folder.parent / "global_daily_counts.parquet")}
        (FORMAT PARQUET,COMPRESSION ZSTD)""")
    connection.execute(f"""COPY (SELECT cell8,NULL::INTEGER AS year,true AS is_static,
        'geographic_auxiliary' AS reason,urban,water,volcano FROM cells
        WHERE urban OR water OR volcano UNION ALL SELECT p.cell8,p.year,true,
        'persistent_source',c.urban,c.water,c.volcano FROM persistence p JOIN cells c USING(cell8)
        UNION ALL SELECT s.cell8,NULL::INTEGER,true,'prior_MODIS_static_catalog',
        c.urban,c.water,c.volcano FROM static_catalog s JOIN cells c USING(cell8))
        TO {sql_literal(folder.parent / "static_source_mask.parquet")}
        (FORMAT PARQUET,COMPRESSION ZSTD)""")
    return {
        "gaps_by_reason": connection.execute(
            "SELECT scope,reason,count(*) FROM data_gaps GROUP BY ALL ORDER BY 1,2"
        ).fetchall(),
        "suspicious_days": connection.execute(
            "SELECT platform,count(*) FROM quality WHERE suspicious_day GROUP BY 1 ORDER BY 1"
        ).fetchall(),
        "coverage": connection.execute(
            "SELECT * FROM coverage ORDER BY platform,processing"
        ).fetchall(),
    }


def monthly_pairs(
    connection: Any,
    sampling: str,
    *,
    countries: set[str] | None = None,
    first_year: int = MIN_TRAINING_YEAR,
    last_year: int = RESERVED_TEST_YEAR + 1,
) -> list[MonthlyPair]:
    """Pares en los mismos días válidos; NRT no participa en el ajuste."""
    source_platforms = (
        "('Terra','Aqua')"
        if sampling == "terra_aqua"
        else ("('Terra')" if sampling == "terra_only" else "('NOAA-20')")
    )
    extra = " AND coalesce(a.valid AND a.standard,false)" if sampling == "terra_aqua" else ""
    source_quality = "t" if sampling in {"terra_aqua", "terra_only"} else "j"
    country_values = ",".join(
        "(" + sql_literal(c) + ")" for c in sorted(countries or HISTORICAL_COUNTRIES)
    )
    official_source = (
        "('Terra (MODIS)','Aqua (MODIS)')"
        if sampling == "terra_aqua"
        else ("('Terra (MODIS)')" if sampling == "terra_only" else "('NOAA-20 (VIIRS)')")
    )
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE common_days AS SELECT c.country,r.day
        FROM (VALUES {country_values}) c(country) CROSS JOIN quality r
        LEFT JOIN quality t ON t.day=r.day AND t.platform='Terra'
        LEFT JOIN quality a ON a.day=r.day AND a.platform='Aqua'
        LEFT JOIN quality j ON j.day=r.day AND j.platform='NOAA-20'
        WHERE r.platform='S-NPP' AND r.valid AND r.standard
        AND coalesce({source_quality}.valid AND {source_quality}.standard,false){extra}
        AND year(r.day) BETWEEN {first_year} AND {last_year}
        AND NOT (c.country='United States of America' AND EXISTS(
            SELECT 1 FROM official_missing_dates o WHERE o.day::DATE=r.day AND o.quality='SP'
            AND (o.satellite='Suomi NPP (VIIRS)' OR o.satellite IN {official_source})))""")
    query = f"""WITH s AS (
        SELECT cell,day,min(country) country,min(biome) biome
        FROM activity s WHERE processing='SP' AND platform IN {source_platforms}
        AND EXISTS(SELECT 1 FROM common_days d WHERE d.day=s.day AND d.country=s.country)
        GROUP BY cell,day
    ),r AS (
        SELECT cell,day,country,biome FROM activity r WHERE processing='SP' AND platform='S-NPP'
        AND EXISTS(SELECT 1 FROM common_days d WHERE d.day=r.day AND d.country=r.country)
    ),paired AS (
        SELECT coalesce(s.cell,r.cell) AS cell,coalesce(s.day,r.day) AS day,
            coalesce(s.country,r.country) country,coalesce(s.biome,r.biome) biome,
            s.cell IS NOT NULL AS x,r.cell IS NOT NULL AS y
        FROM s FULL JOIN r ON s.cell=r.cell AND s.day=r.day
    ), monthly AS (
        SELECT country,biome,year(day) AS year,month(day) AS month,
            sum(x::INTEGER) x,sum(y::INTEGER) y,count(DISTINCT cell) cells
        FROM paired GROUP BY ALL
    ),support AS (
        SELECT country,year(day) AS year,month(day) AS month,count(*) AS days
        FROM common_days GROUP BY ALL
    ),domains AS (
        SELECT DISTINCT country,biome FROM activity
        WHERE processing='SP' AND year(day) BETWEEN {first_year} AND {last_year}
    ),scaffold AS (
        SELECT d.country,d.biome,s.year,s.month,s.days FROM domains d
        JOIN support s USING(country)
    ) SELECT s.country,s.biome,s.year,s.month,coalesce(m.x,0),coalesce(m.y,0),
        coalesce(m.cells,0),s.days FROM scaffold s
        LEFT JOIN monthly m USING(country,biome,year,month)
        ORDER BY country,biome,year,month"""
    result = []
    for country, biome, year, month, x, y, cells, days in connection.execute(query).fetchall():
        expected = calendar.monthrange(int(year), int(month))[1]
        eligible = (expected - int(days)) / expected <= MAX_BAD_DAY_FRACTION
        result.append(
            MonthlyPair(
                str(country),
                int(biome),
                int(year),
                int(month),
                sampling,
                float(x),
                float(y),
                int(cells),
                eligible,
            )
        )
    return result


def reserved_test(pairs: list[MonthlyPair]) -> dict[str, Any]:
    """2024–2025 permanecen fuera del ajuste que produce estas predicciones."""
    training = [p for p in pairs if p.year < RESERVED_TEST_YEAR]
    coefficients = fit_coefficients(training)
    tested = []
    for pair in pairs:
        if not pair.eligible or pair.year not in {2024, 2025}:
            continue
        coefficient = select_coefficient(
            coefficients, pair.country, pair.biome, pair.month, pair.sampling
        )
        if coefficient:
            tested.append(
                {**asdict(pair), "prediction": pair.source_count * coefficient.coefficient}
            )
    return {
        "training_years": sorted({p.year for p in training if p.eligible}),
        "test_years": [2024, 2025],
        "metrics": relative_metrics(
            [p["prediction"] for p in tested], [p["reference_count"] for p in tested]
        ),
        "raw_baseline": relative_metrics(
            [p["source_count"] for p in tested], [p["reference_count"] for p in tested]
        ),
        "predictions": tested,
    }


def transfer_diagnostic(connection: Any, sampling: str, coefficients: list[Any]) -> dict[str, Any]:
    """Prueba geográfica reciente; no convierte un año en validación histórica."""
    countries = {
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT country FROM activity WHERE year(day)=2026"
        ).fetchall()
    } - HISTORICAL_COUNTRIES
    pairs = monthly_pairs(
        connection, sampling, countries=countries, first_year=2026, last_year=2026
    )
    predicted = []
    for pair in pairs:
        coefficient = select_coefficient(
            coefficients, pair.country, pair.biome, pair.month, pair.sampling
        )
        if pair.eligible and coefficient:
            predicted.append(
                {
                    **asdict(pair),
                    "prediction": pair.source_count * coefficient.coefficient,
                    "fallback_level": coefficient.fallback_level,
                }
            )
    return {
        "kind": "geographic_diagnostic_only",
        "year": 2026,
        "coverage_basis": "observed_dates_only",
        "historical_validity_proven": False,
        "countries": sorted(countries),
        "predictions": predicted,
        "metrics": relative_metrics(
            [p["prediction"] for p in predicted], [p["reference_count"] for p in predicted]
        ),
        "raw_baseline": relative_metrics(
            [p["source_count"] for p in predicted], [p["reference_count"] for p in predicted]
        ),
    }


def build_model(workspace: Path) -> dict[str, Any]:
    """Evalúa puertas antes de permitir que la API sirva el producto común."""
    folder = workspace / "source/interim/harmonization"
    reports = workspace / "source/reports"
    prepared = read_json(folder / "prepared.json")
    catalog = snapshot_catalog(workspace)
    base = prepared["input_reports"][0]
    observed_windows = observed_coverage(workspace, base["sha256"], int(base["accepted"]))
    connection = connect(folder / "candidate.duckdb")
    try:
        quality_table(connection, prepared, catalog)
        quality_report = save_quality(connection, folder)
        write_json(
            reports / f"qa_{METHOD_VERSION}.json",
            {
                **prepared,
                "method_version": METHOD_VERSION,
                "input_mask_method_version": prepared["method_version"],
                **quality_report,
                "low_confidence_fraction": prepared["qa_reasons"].get("low_confidence", 0)
                / max(1, sum(prepared["qa_reasons"].values())),
            },
        )
        model_pairs: list[MonthlyPair] = []
        validations = {}
        tests = {}
        coefficients = []
        for sampling in ["terra_only", "terra_aqua", "noaa20"]:
            pairs = monthly_pairs(connection, sampling)
            model_pairs.extend(pairs)
            validation = validate_years(pairs, max_bias=0.05 if sampling == "noaa20" else 0.10)
            tests[sampling] = reserved_test(pairs)
            validations[sampling] = validation
            coefficients.extend(fit_coefficients(pairs))
            log(
                "validation",
                sampling=sampling,
                pairs=len(pairs),
                passed=validation["passed"],
                passed_fraction=validation["passed_fraction"],
                overall=validation["overall"],
                reserved_test=tests[sampling]["metrics"],
            )
        # ADR 0006: MODIS strata are judged only where the same-instrument bridge (NOAA-20 vs S-NPP)
        # can order months; the 0.4.0 result stays visible as strict_passed_fraction.
        for sampling in ["terra_only", "terra_aqua"]:
            validations[sampling] = apply_noise_ceiling(validations[sampling], validations["noaa20"])
            log(
                "noise_ceiling",
                sampling=sampling,
                passed=validations[sampling]["passed"],
                passed_fraction=validations[sampling]["passed_fraction"],
                strict_passed_fraction=validations[sampling]["strict_passed_fraction"],
                below_noise_ceiling=validations[sampling]["below_noise_ceiling"],
            )
        country_transfer = {
            sampling: validate_countries(
                [p for p in model_pairs if p.sampling == sampling],
                max_bias=0.05 if sampling == "noaa20" else 0.10,
            )
            for sampling in ["terra_aqua", "noaa20"]
        }
        log(
            "country_transfer",
            **{s: v["passed_fraction"] for s, v in country_transfer.items()},
        )
        configuration = {
            "h3_resolution": H3_RES,
            "static_resolution": STATIC_SOURCE_H3_RES,
            "static_min_days": STATIC_SOURCE_MIN_DAYS_PER_YEAR,
            "min_confidence": MIN_CONFIDENCE_CLASS,
            "target": "S-NPP active cell-days",
            "minimum_cells": 30,
            "model": "poisson_offset",
            "fallback": ["country_biome", "world_biome", "country", "global"],
            "gate_rule": "noise_ceiling_0.5.0",
            "calibration_countries": sorted(HISTORICAL_COUNTRIES),
            "lifecycle": prepared["sensor_lifecycle"],
            "known_gaps": prepared["known_gaps"],
            "auxiliary_revision": [
                {k: item[k] for k in ["name", "version", "sha256", "derived_sha256"] if k in item}
                for item in prepared["auxiliaries"]
            ],
            "filters": prepared["filter_configuration"],
            "static_source_catalog": prepared.get("static_catalog", {"method": "none"}),
            "input_mask_method_version": prepared["method_version"],
            "catalog": {key: catalog[key] for key in ["availability", "missing_dates"]},
            "observed_coverage": observed_windows,
        }
        identifier = artifact_id(configuration, prepared["input_revision"])
        transfers = {
            sampling: transfer_diagnostic(connection, sampling, coefficients)
            for sampling in ["terra_aqua", "noaa20"]
        }
        gates = {
            "static_mask": bool(prepared["mask_validation"]["passed"]),
            **{key: bool(value["passed"]) for key, value in validations.items()},
        }
        model = {
            "id": identifier,
            "method_version": METHOD_VERSION,
            "input_revision": prepared["input_revision"],
            "configuration": configuration,
            "coefficients": [asdict(c) for c in coefficients],
            "validation": validations,
            "reserved_tests": tests,
            "geographic_diagnostic": transfers,
            "country_transfer": country_transfer,
            "gates": gates,
            "quality": quality_report,
            "publishable": all(gates.values()),
            "local_cloud_opportunities": "not_reconstructed",
            "unit": "equivalent_VIIRS_active_cell_days",
            "synthetic": False,
        }
        write_json(reports / f"validation_{METHOD_VERSION}.json", model)
        write_json(reports / f"inter_viirs_bridge_{METHOD_VERSION}.json", validations["noaa20"])
        write_json(folder / "model.json", model)
        write_json(
            folder / "status.json",
            {
                "id": identifier,
                "method_version": METHOD_VERSION,
                "status": "validated_pending_acceptance"
                if model["publishable"]
                else "candidate_failed_validation",
                "gates": gates,
                "unit": model["unit"],
                "synthetic": False,
                "mask_validation": prepared["mask_validation"],
                "validation": {
                    key: {k: v for k, v in value.items() if k not in {"predictions", "strata"}}
                    for key, value in validations.items()
                },
                "country_transfer": {
                    key: {k: v for k, v in value.items() if k != "countries"}
                    for key, value in country_transfer.items()
                },
                "local_cloud_opportunities": "not_reconstructed",
            },
        )
        write_json(folder / "monthly_pairs.json", [asdict(p) for p in model_pairs])
        frame = pd.DataFrame.from_records([asdict(c) for c in coefficients])
        connection.register("coefficient_frame", frame)
        connection.execute(
            "CREATE OR REPLACE TABLE coefficients AS SELECT * FROM coefficient_frame"
        )
        connection.unregister("coefficient_frame")
        destination = reports.parent / "harmonized" / f"calibration_{METHOD_VERSION}.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        path = str(destination).replace("'", "''")
        connection.execute(f"""COPY (SELECT country||':'||biome AS stratum,month,
            sampling AS sampling_stratum,n,coefficient AS coef,fallback_level,years
            FROM coefficients ORDER BY country,biome,month,sampling)
            TO '{path}' (FORMAT PARQUET,COMPRESSION ZSTD)""")
        connection.execute("CHECKPOINT")
        log("model_ready", id=identifier, gates=gates, publishable=model["publishable"])
        return model
    finally:
        connection.close()


def main() -> None:
    """CLI separada de la web; deja candidatos y reportes incluso al fallar una puerta."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = build_model(args.workspace.resolve())
    if not result["publishable"]:
        raise SystemExit("El candidato no supera todas las puertas científicas; no se publica")


if __name__ == "__main__":
    main()
