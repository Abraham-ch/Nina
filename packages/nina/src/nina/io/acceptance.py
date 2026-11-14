"""Informe reproducible de aceptación; las puertas fallidas permanecen fallidas."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from nina.calibration import relative_metrics
from nina.io.harmonization import file_digest, read_json, write_json

EARLY_FIRST_YEAR, EARLY_LAST_YEAR = 2012, 2014
MAX_CONTINUITY_BIAS = 0.10


def test_evidence(path: Path) -> dict[str, Any]:
    """Lee el resultado real de pytest, sin interpretar su salida de consola."""
    if not path.exists():
        return {"passed": False, "tests": 0, "evidence": str(path)}
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failed = sum(
        any(child.tag in {"failure", "error", "skipped"} for child in case) for case in cases
    )
    return {
        "passed": bool(cases) and failed == 0,
        "tests": len(cases),
        "failed": failed,
        "evidence": str(path),
        "names": sorted(case.attrib["name"] for case in cases),
    }


def early_continuity(model: dict[str, Any]) -> dict[str, Any]:
    """Diferencia sobre 2012–2014: los años están fuera de su propio ajuste."""
    pairs = model["validation"]["terra_aqua"]["predictions"]
    countries = sorted({p["country"] for p in pairs})
    rows = []
    for country in countries:
        selected = [
            p
            for p in pairs
            if p["country"] == country and EARLY_FIRST_YEAR <= p["year"] <= EARLY_LAST_YEAR
        ]
        metrics = relative_metrics(
            [p["prediction"] for p in selected], [p["reference_count"] for p in selected]
        )
        bias = metrics["relative_bias"]
        rows.append(
            {
                "country": country,
                **metrics,
                "passed": bias is not None and abs(bias) <= MAX_CONTINUITY_BIAS,
            }
        )
    return {"countries": rows, "passed": bool(rows) and all(row["passed"] for row in rows)}


def acceptance(workspace: Path) -> dict[str, Any]:
    """Comprueba evidencias y escribe el resultado aunque el candidato no sea publicable."""
    folder = workspace / "source/interim/harmonization"
    reports = workspace / "source/reports"
    prepared, model = read_json(folder / "prepared.json"), read_json(folder / "model.json")
    qa_path = reports / f"qa_{model['method_version']}.json"
    qa = read_json(qa_path)
    schema = read_json(workspace / "docs/reference/qa_report.schema.json")
    schema_errors = [error.message for error in Draft202012Validator(schema).iter_errors(qa)]
    tests = {
        name: test_evidence(reports / filename)
        for name, filename in [
            ("scientific", "tests-scientific.xml"),
            ("mvp", "tests-mvp.xml"),
            ("harmonized_api", "tests-harmonized-api.xml"),
        ]
    }
    code_checks_path = reports / "technical-checks.json"
    code_checks = read_json(code_checks_path) if code_checks_path.exists() else {"exit_code": None}
    row_accounting = all(
        r["rows_read"] == r["accepted"] + sum(r["rejected"].values())
        for r in prepared["input_reports"]
    )
    normalized = (
        sum(r["accepted"] for r in prepared["input_reports"]) - prepared["cross_input_duplicates"]
    )
    row_accounting = row_accounting and sum(prepared["qa_reasons"].values()) == normalized
    auxiliary_integrity = all(
        file_digest(Path(item["path"])) == item["sha256"] for item in prepared["auxiliaries"]
    )
    continuity = early_continuity(model)
    checks = [
        ("OUT-01", row_accounting, "Cuadre por archivo, duplicados y motivos de descarte"),
        ("OUT-02", not schema_errors, "qa_report.schema.json y reporte QA"),
        (
            "AUX-01/02/03",
            auxiliary_integrity,
            "SHA-256, versión y licencia de cinco fuentes auxiliares",
        ),
        ("HAR-04", continuity["passed"], "Predicciones dejando años fuera sobre 2012–2014"),
        (
            "TYPE-04",
            model["gates"]["static_mask"],
            "Recuperación ≥80 % y retirada de vegetación ≤2 %",
        ),
        (
            "HAR-03 · Terra",
            model["gates"]["terra_only"],
            "Sesgo ≤10 % y Spearman ≥0,8 en ≥80 % de estratos",
        ),
        (
            "HAR-03 · Terra+Aqua",
            model["gates"]["terra_aqua"],
            "Sesgo ≤10 % y Spearman ≥0,8 en ≥80 % de estratos",
        ),
        (
            "SRC-02",
            model["gates"]["noaa20"],
            "Puente NOAA-20, sesgo ≤5 % en los estratos evaluables",
        ),
        (
            "Pruebas de procesamiento y contrato",
            all(t["passed"] for t in tests.values()),
            "Informes JUnit de los tres conjuntos de pruebas",
        ),
        (
            "Lint y tipos",
            code_checks.get("exit_code") == 0,
            "technical-checks.json y monorepo-checks.log",
        ),
        (
            "Versión de entrada",
            model["configuration"]["input_mask_method_version"] == prepared["method_version"],
            "El entrenamiento corresponde al filtro activo",
        ),
    ]
    criteria = [
        {"criterion": code, "status": "cumple" if passed else "no cumple", "evidence": evidence}
        for code, passed, evidence in checks
    ]
    specification = (workspace / "docs/ACCEPTANCE_CRITERIA.md").read_text(encoding="utf-8")
    mandatory_ids = re.findall(r"^\*\*([A-Z]+-\d+) \[OBL\]", specification, re.MULTILINE)
    verified = {c["criterion"]: c for c in criteria}
    verified["HAR-03"] = {
        "criterion": "HAR-03",
        "status": "cumple"
        if model["gates"]["terra_only"] and model["gates"]["terra_aqua"]
        else "no cumple",
        "evidence": f"validation_{model['method_version']}.json: Terra y Terra+Aqua",
    }
    mandatory = [
        verified.get(
            code,
            {
                "criterion": code,
                "status": "pendiente",
                "evidence": "La evidencia de este criterio completo aún no está auditada",
            },
        )
        for code in mandatory_ids
    ]
    result = {
        "id": model["id"],
        "method_version": model["method_version"],
        "input_revision": model["input_revision"],
        "publishable": bool(mandatory)
        and all(p for _, p, _ in checks)
        and all(c["status"] == "cumple" for c in mandatory),
        "criteria": criteria,
        "mandatory_criteria": mandatory,
        "tests": tests,
        "schema_errors": schema_errors,
        "early_continuity": continuity,
        "recommended_pending": [
            "GAP-05: nubosidad y oportunidades locales no reconstruidas",
            "HAR-06: contraste con área quemada MCD64A1",
            "PIX-03: sensibilidad al ángulo de barrido",
        ],
    }
    write_json(reports / f"acceptance_{model['id']}.json", result)
    lines = [
        f"# Aceptación · {model['id']}",
        "",
        f"Método: {model['method_version']}.",
        "",
        "| Criterio | Estado | Evidencia |",
        "|---|---|---|",
    ]
    lines.extend(f"| {c['criterion']} | {c['status']} | {c['evidence']} |" for c in criteria)
    lines.extend(
        [
            "",
            "## Auditoría de todos los criterios obligatorios",
            "",
            "Un control técnico parcial no certifica por sí solo el criterio completo.",
            "Los criterios sin evidencia auditada siguen pendientes y bloquean la publicación.",
            "",
            "| Criterio | Estado | Evidencia |",
            "|---|---|---|",
            *[f"| {c['criterion']} | {c['status']} | {c['evidence']} |" for c in mandatory],
        ]
    )
    lines.extend(
        [
            "",
            "Resultado: "
            + (
                "apto para publicación"
                if result["publishable"]
                else "no apto para publicación científica"
            ),
            "",
            "La ingesta original, las consultas observadas y la interfaz previa "
            "conservan su propio contrato.",
            "Este informe evalúa el candidato y sus nuevas etapas de armonización.",
            "",
            "Extensiones recomendadas pendientes:",
            *["- " + x for x in result["recommended_pending"]],
        ]
    )
    (reports / f"acceptance_{model['id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> None:
    """CLI para regenerar el informe con los resultados presentes en source/reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = acceptance(args.workspace.resolve())
    print(json.dumps({"id": result["id"], "publishable": result["publishable"]}))
    if not result["publishable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
