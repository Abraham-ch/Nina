"""Pruebas del método con pares agregados pequeños, nunca datos de producción."""

from datetime import date, timedelta

import pytest
from nina.calibration import (
    MonthlyPair,
    artifact_id,
    fit_coefficients,
    historical_summary,
    validate_years,
)
from nina.coverage import confidence_class, daily_quality, month_eligible


def pairs():
    return [
        MonthlyPair("Peru", 1, year, month, "terra_aqua", float(month * 10), float(month * 20), 40)
        for year in range(2018, 2024)
        for month in range(1, 13)
    ]


def test_calibration_recovers_reference_with_reserved_years():
    data = pairs()
    validation = validate_years(data)
    assert validation["passed"] and validation["passed_fraction"] == 1
    assert abs(validation["overall"]["relative_bias"]) < 1e-10
    assert validation["overall"]["spearman"] > 0.99
    assert all(c.coefficient == 2 for c in fit_coefficients(data))


def test_a_test_year_never_contributes_to_its_own_coefficient():
    data = [
        p
        if p.year != 2023
        else MonthlyPair(
            p.country,
            p.biome,
            p.year,
            p.month,
            p.sampling,
            p.source_count,
            p.reference_count * 10,
            p.active_cells,
        )
        for p in pairs()
    ]
    output = validate_years(data)
    held = [r for r in output["predictions"] if r["year"] == 2023]
    assert held and all(r["coefficient"] == 2 for r in held)
    assert not output["passed"]


def test_nothing_is_calibrated_without_support():
    assert fit_coefficients(pairs()[:12]) == []
    assert validate_years(pairs()[:12])["passed"] is False
    assert historical_summary(10, [1, 2, 3, 4])["historical_median"] is None
    result = historical_summary(12, [2, 4, 6, 8, 10])
    assert result["historical_median"] == 6 and result["anomaly_percent"] == 100


def test_artifact_identity_is_reproducible_and_changes_with_input():
    assert artifact_id({"resolution": 7}, "a") == artifact_id({"resolution": 7}, "a")
    assert artifact_id({"resolution": 7}, "a") != artifact_id({"resolution": 7}, "b")
    assert artifact_id({"date": date(2026, 7, 31)}, "a") == artifact_id({"date": "2026-07-31"}, "a")


def test_outage_and_mission_end_are_different():
    first = date(2026, 10, 1)
    last = first + timedelta(days=39)
    counts = {first + timedelta(days=i): 100 for i in range(40)}
    counts[first + timedelta(days=10)] = 0
    result = daily_quality(counts, first, last, mission_end=first + timedelta(days=30))
    assert result[10]["data_gap"]
    assert result[31]["reason"] == "end_of_mission" and not result[31]["data_gap"]
    assert month_eligible(30, 6) and not month_eligible(30, 7)


@pytest.mark.parametrize(
    ("platform", "raw", "expected"),
    [
        ("Terra", "29", "low"),
        ("Aqua", "30", "nominal"),
        ("Aqua", "79", "nominal"),
        ("Aqua", "80", "high"),
        ("Aqua", "100", "high"),
        ("S-NPP", "l", "low"),
        ("S-NPP", "n", "nominal"),
        ("S-NPP", "h", "high"),
    ],
)
def test_confidence_classes(platform, raw, expected):
    assert confidence_class(platform, raw) == expected


def test_invalid_confidence_is_rejected():
    with pytest.raises(ValueError):
        confidence_class("Aqua", "101")
    with pytest.raises(ValueError):
        confidence_class("S-NPP", "unknown")


def test_validation_reports_per_year_error_and_raw_baseline():
    from nina.calibration import MonthlyPair, validate_years, yearly_error_summary

    pairs = [
        MonthlyPair("Peru", 1, year, month, "terra_aqua", 100.0 + 10 * month, (300.0 + 30 * month) * (1.08 if year % 2 else 0.93), 50)
        for year in range(2012, 2024)
        for month in range(1, 13)
    ]
    result = validate_years(pairs)
    stratum = result["strata"][0]
    assert len(stratum["yearly_relative_bias"]) == 12
    assert stratum["yearly_abs_bias_median"] > 0.05  # el sesgo agregado oculta ±7 % por año
    assert abs(stratum["relative_bias"]) < 0.05
    assert stratum["raw_spearman"] is not None
    assert result["per_year_error_in_passed_strata"]["years_within_10pct"] is not None
    assert yearly_error_summary([0.05, -0.2, 0.08])["years_within_10pct"] == 2 / 3
