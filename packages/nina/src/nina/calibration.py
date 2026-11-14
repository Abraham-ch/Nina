"""Calibración reproducible de actividad observada; no realiza entrada/salida."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from scipy.stats import spearmanr

from nina.config import HARMONIZATION_VERSION

METHOD_VERSION = HARMONIZATION_VERSION
REFERENCE_FIRST_YEAR = 2012
MIN_FIT_YEARS = 3
MIN_VALIDATION_YEARS = 5
MIN_STRATUM_MONTHS = 24
MIN_SPEARMAN = 0.8
MIN_PASS_FRACTION = 0.8
MIN_HISTORY_YEARS = 5


@dataclass(frozen=True)
class MonthlyPair:
    """Un agregado comparable de archivo estándar, con sus condiciones explícitas."""

    country: str
    biome: int
    year: int
    month: int
    sampling: str
    source_count: float
    reference_count: float
    active_cells: int
    eligible: bool = True


@dataclass(frozen=True)
class Coefficient:
    country: str
    biome: int
    month: int
    sampling: str
    coefficient: float
    n: int
    years: tuple[int, ...]
    fallback_level: str


def relative_metrics(predictions: list[float], reference: list[float]) -> dict[str, Any]:
    """Métricas agregadas; una referencia constante no tiene correlación definida."""
    if not predictions or len(predictions) != len(reference):
        return {
            "n": 0,
            "relative_bias": None,
            "spearman": None,
            "mae": None,
            "rmse": None,
            "r2": None,
        }
    errors = [p - y for p, y in zip(predictions, reference, strict=True)]
    total = sum(reference)
    mean = statistics.mean(reference)
    squares = sum((y - mean) ** 2 for y in reference)
    correlation: float | None = None
    if len(set(predictions)) > 1 and len(set(reference)) > 1:
        correlation = float(spearmanr(predictions, reference).statistic)
    return {
        "n": len(reference),
        "relative_bias": sum(errors) / total if total else None,
        "spearman": correlation,
        "mae": statistics.mean(abs(e) for e in errors),
        "rmse": math.sqrt(statistics.mean(e * e for e in errors)),
        "r2": 1 - sum(e * e for e in errors) / squares if squares > 0 else None,
    }


def fit_coefficients(pairs: list[MonthlyPair], min_cells: int = 30) -> list[Coefficient]:
    """Poisson con offset de actividad: exp(intercepto)=suma(y)/suma(x).

    Se ajustan bioma × país × mes × régimen y sus respaldos país/global.
    El conteo de soporte son celdas-mes, no el número de píxeles detectados.
    """
    groups: dict[tuple[str, int, int, str], list[MonthlyPair]] = defaultdict(list)
    for pair in pairs:
        if not pair.eligible or pair.year < REFERENCE_FIRST_YEAR or pair.source_count <= 0:
            continue
        for key in {
            (pair.country, pair.biome, pair.month, pair.sampling),
            (pair.country, 0, pair.month, pair.sampling),
            ("world", 0, pair.month, pair.sampling),
        }:
            groups[key].append(pair)
    result = []
    for (country, biome, month, sampling), records in sorted(groups.items()):
        x = sum(p.source_count for p in records)
        y = sum(p.reference_count for p in records)
        n = sum(p.active_cells for p in records)
        years = tuple(sorted({p.year for p in records}))
        if n < min_cells or x <= 0 or y <= 0 or len(years) < MIN_FIT_YEARS:
            continue
        result.append(
            Coefficient(
                country,
                biome,
                month,
                sampling,
                y / x,
                n,
                years,
                "biome" if biome else "country" if country != "world" else "global",
            )
        )
    return result


def select_coefficient(
    coefficients: list[Coefficient],
    country: str,
    biome: int,
    month: int,
    sampling: str,
) -> Coefficient | None:
    """Respaldo explícito; nunca inventa un coeficiente para un mes sin soporte."""
    lookup = {(c.country, c.biome, c.month, c.sampling): c for c in coefficients}
    for key in [
        (country, biome, month, sampling),
        (country, 0, month, sampling),
        ("world", 0, month, sampling),
    ]:
        if key in lookup:
            return lookup[key]
    return None


def validate_years(pairs: list[MonthlyPair], max_bias: float = 0.10) -> dict[str, Any]:
    """Validación dejando años completos fuera; cada predicción evita su propio año."""
    eligible = [p for p in pairs if p.eligible and p.year >= REFERENCE_FIRST_YEAR]
    years = sorted({p.year for p in eligible})
    predictions: list[dict[str, Any]] = []
    by_stratum: dict[tuple[str, int, str], list[tuple[float, float]]] = defaultdict(list)
    by_year: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for year in years:
        coefficients = fit_coefficients([p for p in eligible if p.year != year])
        for pair in [p for p in eligible if p.year == year]:
            coefficient = select_coefficient(
                coefficients,
                pair.country,
                pair.biome,
                pair.month,
                pair.sampling,
            )
            if coefficient is None:
                continue
            prediction = pair.source_count * coefficient.coefficient
            value = (prediction, pair.reference_count)
            by_stratum[(pair.country, pair.biome, pair.sampling)].append(value)
            by_year[year].append(value)
            predictions.append(
                {
                    **asdict(pair),
                    "prediction": prediction,
                    "coefficient": coefficient.coefficient,
                    "fallback_level": coefficient.fallback_level,
                }
            )
    strata = []
    for (country, biome, sampling), values in sorted(by_stratum.items()):
        metrics = relative_metrics([v[0] for v in values], [v[1] for v in values])
        bias, correlation = metrics["relative_bias"], metrics["spearman"]
        active_months = sum(p > 0 or y > 0 for p, y in values)
        evaluable = (
            active_months >= MIN_STRATUM_MONTHS and bias is not None and correlation is not None
        )
        passed = evaluable and abs(bias) <= max_bias and correlation >= MIN_SPEARMAN
        strata.append(
            {
                "country": country,
                "biome": biome,
                "sampling": sampling,
                **metrics,
                "active_months": active_months,
                "evaluable": evaluable,
                "passed": bool(passed),
            }
        )
    evaluable_strata = [s for s in strata if s["evaluable"]]
    fraction = (
        sum(s["passed"] for s in evaluable_strata) / len(evaluable_strata)
        if evaluable_strata
        else 0.0
    )
    yearly = {
        str(y): relative_metrics([v[0] for v in values], [v[1] for v in values])
        for y, values in sorted(by_year.items())
    }
    all_metrics = relative_metrics(
        [p["prediction"] for p in predictions], [p["reference_count"] for p in predictions]
    )
    return {
        "method": "leave_one_year_out",
        "years": years,
        "strata": strata,
        "by_year": yearly,
        "overall": all_metrics,
        "passed_fraction": fraction,
        "minimum_fraction": MIN_PASS_FRACTION,
        "max_absolute_bias": max_bias,
        "minimum_spearman": MIN_SPEARMAN,
        "passed": len(years) >= MIN_VALIDATION_YEARS
        and bool(evaluable_strata)
        and fraction >= MIN_PASS_FRACTION,
        "predictions": predictions,
        "zero_source_months": sum(p.source_count == 0 for p in eligible),
    }


def historical_summary(value: float | None, history: list[float]) -> dict[str, Any]:
    """Referencia histórica descriptiva; requiere cinco años anteriores elegibles."""
    if value is None or len(history) < MIN_HISTORY_YEARS:
        return {"historical_median": None, "historical_n": len(history), "anomaly_percent": None}
    median = statistics.median(history)
    return {
        "historical_median": median,
        "historical_n": len(history),
        "anomaly_percent": 100 * (value / median - 1) if median > 0 else None,
    }


def artifact_id(configuration: dict[str, Any], input_revision: str) -> str:
    """Identidad estable del método, configuración y entradas; sin timestamps."""
    payload = {
        "method_version": METHOD_VERSION,
        "configuration": configuration,
        "input_revision": input_revision,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :24
    ]
