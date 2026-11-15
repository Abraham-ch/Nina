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
# Sentinel of the aggregate (all-biome) coefficients. Biome 0 is an ordinary stratum: cells without a RESOLVE
# ecoregion, mostly coastal (ADR 0006). Before 0.5.0 both shared the value 0.
ALL_BIOMES = -1
WORLD = "world"


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

    Fitted levels (ADR 0006): country x biome, world x biome, country (all biomes) and world (all biomes),
    each by month and sampling regime. Support counts cell-months, not detected pixels.
    """
    groups: dict[tuple[str, int, int, str], list[MonthlyPair]] = defaultdict(list)
    for pair in pairs:
        if not pair.eligible or pair.year < REFERENCE_FIRST_YEAR or pair.source_count <= 0:
            continue
        for key in {
            (pair.country, pair.biome, pair.month, pair.sampling),
            (WORLD, pair.biome, pair.month, pair.sampling),
            (pair.country, ALL_BIOMES, pair.month, pair.sampling),
            (WORLD, ALL_BIOMES, pair.month, pair.sampling),
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
                fallback_name(country, biome),
            )
        )
    return result


def fallback_name(country: str, biome: int) -> str:
    """Level of a fitted coefficient, from the most to the least specific."""
    if biome != ALL_BIOMES:
        return "biome" if country != WORLD else "world_biome"
    return "country" if country != WORLD else "global"


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
        (WORLD, biome, month, sampling),
        (country, ALL_BIOMES, month, sampling),
        (WORLD, ALL_BIOMES, month, sampling),
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
    raw: dict[tuple[str, int, str], list[tuple[float, float]]] = defaultdict(list)
    stratum_years: dict[tuple[str, int, str], dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
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
            key = (pair.country, pair.biome, pair.sampling)
            by_stratum[key].append(value)
            by_year[year].append(value)
            raw[key].append((pair.source_count, pair.reference_count))
            stratum_years[key][year][0] += prediction
            stratum_years[key][year][1] += pair.reference_count
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
        yearly_bias = {
            year: total_prediction / total_reference - 1
            for year, (total_prediction, total_reference) in sorted(
                stratum_years[(country, biome, sampling)].items()
            )
            if total_reference > 0
        }
        raw_metrics = relative_metrics(
            [v[0] for v in raw[(country, biome, sampling)]],
            [v[1] for v in raw[(country, biome, sampling)]],
        )
        strata.append(
            {
                "country": country,
                "biome": biome,
                "sampling": sampling,
                **metrics,
                "active_months": active_months,
                "evaluable": evaluable,
                "passed": bool(passed),
                "raw_spearman": raw_metrics["spearman"],
                "yearly_relative_bias": {str(y): b for y, b in yearly_bias.items()},
                **yearly_error_summary(list(yearly_bias.values())),
            }
        )
    evaluable_strata = [s for s in strata if s["evaluable"]]
    fraction = (
        sum(s["passed"] for s in evaluable_strata) / len(evaluable_strata)
        if evaluable_strata
        else 0.0
    )
    passed_yearly = [
        b for s in strata if s["passed"] for b in s["yearly_relative_bias"].values()
    ]
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
        # El sesgo del gate se agrega sobre todos los años; esto muestra el error de cada año
        # en los estratos aprobados (lo que un usuario ve al mirar un año concreto).
        "per_year_error_in_passed_strata": yearly_error_summary(passed_yearly),
        "raw_baseline_passing_spearman": sum(
            1
            for s in evaluable_strata
            if s["raw_spearman"] is not None
            and s["relative_bias"] is not None
            and s["raw_spearman"] >= MIN_SPEARMAN
        ),
    }


def apply_noise_ceiling(validation: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Noise ceiling of ADR 0006: a MODIS stratum is evaluable only where the same-instrument bridge works.

    `reference` is the NOAA-20 vs S-NPP validation. Where NOAA-20 reaches Spearman >= MIN_SPEARMAN in a
    country x biome stratum, monthly ordering is measurable there; where it does not, no calibration of
    MODIS could meet the threshold and the stratum is reported as below the ceiling (never as passed).
    Strata without an evaluable NOAA-20 value stay evaluable. The 0.4.0 result is kept as `strict_*`.
    """
    ceiling = {
        (s["country"], s["biome"]): s["spearman"]
        for s in reference.get("strata", [])
        if s.get("evaluable") and s.get("spearman") is not None
    }
    strata = []
    for stratum in validation["strata"]:
        value = ceiling.get((stratum["country"], stratum["biome"]))
        below = bool(stratum["evaluable"] and value is not None and value < MIN_SPEARMAN)
        strata.append(
            {
                **stratum,
                "noise_ceiling_spearman": value,
                "below_noise_ceiling": below,
                "strict_evaluable": stratum["evaluable"],
                "strict_passed": stratum["passed"],
                "evaluable": bool(stratum["evaluable"] and not below),
                "passed": bool(stratum["passed"] and not below),
            }
        )
    strict = [s for s in strata if s["strict_evaluable"]]
    evaluable = [s for s in strata if s["evaluable"]]
    fraction = sum(s["passed"] for s in evaluable) / len(evaluable) if evaluable else 0.0
    strict_fraction = sum(s["strict_passed"] for s in strict) / len(strict) if strict else 0.0
    return {
        **validation,
        "strata": strata,
        "passed_fraction": fraction,
        "strict_passed_fraction": strict_fraction,
        "below_noise_ceiling": sum(s["below_noise_ceiling"] for s in strata),
        "evaluable_strata": len(evaluable),
        "passed": len(validation["years"]) >= MIN_VALIDATION_YEARS
        and bool(evaluable)
        and fraction >= MIN_PASS_FRACTION,
        "strict_passed": bool(validation["passed"]),
        "gate_rule": "noise_ceiling_0.5.0",
    }


def validate_countries(pairs: list[MonthlyPair], max_bias: float = 0.10) -> dict[str, Any]:
    """Leave-country-out transfer test (reported, not gated): predict each country without its own data.

    Coefficients are fitted on every other calibration country, so a country's months are predicted
    through the world x biome level (world, all biomes, when that biome is absent elsewhere).
    """
    eligible = [p for p in pairs if p.eligible and p.year >= REFERENCE_FIRST_YEAR]
    countries = sorted({p.country for p in eligible})
    results = []
    for country in countries:
        coefficients = fit_coefficients([p for p in eligible if p.country != country])
        lookup = {(c.country, c.biome, c.month, c.sampling): c for c in coefficients}
        monthly: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        levels: dict[str, int] = defaultdict(int)
        for pair in (p for p in eligible if p.country == country):
            coefficient = next(
                (
                    lookup[key]
                    for key in [
                        (WORLD, pair.biome, pair.month, pair.sampling),
                        (WORLD, ALL_BIOMES, pair.month, pair.sampling),
                    ]
                    if key in lookup
                ),
                None,
            )
            if coefficient is None:
                continue
            levels[coefficient.fallback_level] += 1
            totals = monthly[(pair.year, pair.month)]
            totals[0] += pair.source_count * coefficient.coefficient
            totals[1] += pair.reference_count
            totals[2] += pair.source_count
        values = [v for _, v in sorted(monthly.items()) if v[1] > 0 or v[0] > 0]
        metrics = relative_metrics([v[0] for v in values], [v[1] for v in values])
        raw = relative_metrics([v[2] for v in values], [v[1] for v in values])
        bias, correlation = metrics["relative_bias"], metrics["spearman"]
        results.append(
            {
                "country": country,
                **metrics,
                "raw_relative_bias": raw["relative_bias"],
                "raw_spearman": raw["spearman"],
                "months": len(values),
                "fallback_levels": dict(levels),
                "passed": bool(
                    bias is not None
                    and correlation is not None
                    and abs(bias) <= max_bias
                    and correlation >= MIN_SPEARMAN
                ),
            }
        )
    scored = [r for r in results if r["relative_bias"] is not None]
    return {
        "method": "leave_one_country_out",
        "kind": "reported_not_gated",
        "countries": results,
        "passed_fraction": sum(r["passed"] for r in scored) / len(scored) if scored else None,
        "median_absolute_bias": statistics.median(abs(r["relative_bias"]) for r in scored)
        if scored
        else None,
        "max_absolute_bias": max_bias,
        "minimum_spearman": MIN_SPEARMAN,
    }


def yearly_error_summary(biases: list[float]) -> dict[str, Any]:
    """Error relativo por año: mediana y percentil 90 del valor absoluto, y fracción ≤10 %."""
    if not biases:
        return {"yearly_abs_bias_median": None, "yearly_abs_bias_p90": None, "years_within_10pct": None}
    absolute = sorted(abs(b) for b in biases)
    p90 = absolute[min(len(absolute) - 1, math.ceil(0.9 * len(absolute)) - 1)]
    return {
        "yearly_abs_bias_median": statistics.median(absolute),
        "yearly_abs_bias_p90": p90,
        "years_within_10pct": sum(b <= 0.10 for b in absolute) / len(absolute),
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
