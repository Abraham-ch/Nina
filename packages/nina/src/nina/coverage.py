"""Calidad temporal basada en el soporte del archivo; no infiere cielo despejado."""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any

ROLLING_RADIUS = 15
OUTAGE_FRACTION = 0.10
# Un hueco documentado (Readme de FIRMS) solo se confirma si el conteo cae por debajo de esta
# fracción de la mediana móvil; con datos normales queda como aviso (ADR 0005).
KNOWN_GAP_CONFIRMATION_FRACTION = 0.50
SUSPICIOUS_MADS = 5
MAX_BAD_DAY_FRACTION = 0.20
MIN_AGGREGATION_DAYS = 8


def daily_quality(
    counts: dict[date, int],
    first: date,
    last: date,
    *,
    mission_end: date | None = None,
    known_missing: set[date] | None = None,
    known_candidates: set[date] | None = None,
) -> list[dict[str, Any]]:
    """Diagnóstico de interrupciones con una zona amplia de referencia.

    `known_missing` fuerza el hueco (falla de hardware oficial). `known_candidates` son huecos
    documentados que se confirman con el conteo diario: si el satélite registró actividad
    normal ese día, el día sigue válido y se anota `known_gap_unconfirmed`.

    El conteo global bajo es una advertencia de soporte, nunca un porcentaje de
    nubosidad ni una certificación de observabilidad de cada región.
    """
    known = set(known_missing or set())
    candidates = known_candidates or set()
    result = []
    day = first
    while day <= last:
        if mission_end and day > mission_end:
            result.append(
                {
                    "day": day,
                    "n": 0,
                    "data_gap": False,
                    "reason": "end_of_mission",
                    "suspicious_day": False,
                }
            )
            day += timedelta(days=1)
            continue
        window = [
            counts.get(day + timedelta(days=offset), 0)
            for offset in range(-ROLLING_RADIUS, ROLLING_RADIUS + 1)
            if first <= day + timedelta(days=offset) <= last
            and (not mission_end or day + timedelta(days=offset) <= mission_end)
        ]
        median = statistics.median(window) if window else 0
        mad = statistics.median(abs(value - median) for value in window) if window else 0
        n = counts.get(day, 0)
        confirmed = day in known or (
            day in candidates
            and (n == 0 or (median > 0 and n < KNOWN_GAP_CONFIRMATION_FRACTION * median))
        )
        missing = confirmed or n == 0 or (median > 0 and n < OUTAGE_FRACTION * median)
        suspicious = mad > 0 and abs(n - median) > SUSPICIOUS_MADS * mad
        result.append(
            {
                "day": day,
                "n": n,
                "data_gap": missing,
                "reason": "known_or_official_gap"
                if confirmed
                else "detected_outage"
                if missing
                else "known_gap_unconfirmed"
                if day in candidates
                else "archive_activity_present",
                "suspicious_day": suspicious,
            }
        )
        day += timedelta(days=1)
    return result


def month_eligible(days_expected: int, bad_days: int) -> bool:
    """Umbral documentado; un mes incompleto no entra en la climatología."""
    return days_expected >= MIN_AGGREGATION_DAYS and (
        bad_days / days_expected <= MAX_BAD_DAY_FRACTION
    )


def confidence_class(platform: str, value: str) -> str:
    """La confianza se clasifica para filtrar, nunca para ponderar actividad."""
    if platform in {"Terra", "Aqua"}:
        number = float(value)
        nominal_threshold, high_threshold, maximum = 30, 80, 100
        if not 0 <= number <= maximum:
            raise ValueError("Confianza MODIS fuera de rango")
        return (
            "low"
            if number < nominal_threshold
            else "nominal"
            if number < high_threshold
            else "high"
        )
    result = {"l": "low", "n": "nominal", "h": "high"}.get(value.lower())
    if result is None:
        raise ValueError("Confianza VIIRS desconocida")
    return result
