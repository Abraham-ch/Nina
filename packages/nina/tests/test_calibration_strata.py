"""Method 0.5.0 (ADR 0006): own stratum for cells without ecoregion, world x biome fallback, noise ceiling
and the leave-country-out transfer test."""

from nina.calibration import (
    ALL_BIOMES,
    WORLD,
    MonthlyPair,
    apply_noise_ceiling,
    fit_coefficients,
    select_coefficient,
    validate_countries,
)


def pairs(country: str, biome: int, ratio: float, cells: int = 40, years=range(2012, 2018)) -> list[MonthlyPair]:
    return [
        MonthlyPair(country, biome, year, month, "terra_aqua", 10.0 + month, (10.0 + month) * ratio, cells)
        for year in years
        for month in range(1, 13)
    ]


def test_cells_without_ecoregion_get_their_own_coefficient():
    # Coastal cells (biome 0) have a far higher VIIRS/MODIS ratio than the country as a whole.
    data = pairs("Peru", 1, 3.0) + pairs("Peru", 0, 20.0)
    coefficients = fit_coefficients(data)
    coastal = select_coefficient(coefficients, "Peru", 0, 6, "terra_aqua")
    country = select_coefficient(coefficients, "Peru", ALL_BIOMES, 6, "terra_aqua")
    assert coastal is not None and coastal.fallback_level == "biome"
    assert abs(coastal.coefficient - 20.0) < 1e-9
    assert country is not None and country.fallback_level == "country"
    assert 3.0 < country.coefficient < 20.0


def test_a_biome_without_local_support_uses_the_same_biome_elsewhere():
    data = pairs("Brazil", 7, 4.0) + pairs("Brazil", 1, 2.0) + pairs("Peru", 1, 2.0)
    coefficients = fit_coefficients(data)
    chosen = select_coefficient(coefficients, "Peru", 7, 8, "terra_aqua")
    assert chosen is not None
    assert chosen.country == WORLD and chosen.fallback_level == "world_biome"
    assert abs(chosen.coefficient - 4.0) < 1e-9
    # An unknown biome falls back to the country, then to the world.
    other = select_coefficient(coefficients, "Peru", 9, 8, "terra_aqua")
    assert other is not None and other.fallback_level == "country"
    assert select_coefficient(coefficients, "Chile", 9, 8, "terra_aqua").fallback_level == "global"


def stratum(country, biome, passed, spearman=0.9, evaluable=True):
    return {"country": country, "biome": biome, "passed": passed, "evaluable": evaluable, "spearman": spearman}


def test_noise_ceiling_excludes_strata_the_reference_instrument_cannot_order():
    modis = {
        "years": list(range(2012, 2026)),
        "passed": False,
        "strata": [
            stratum("Peru", 1, True),
            stratum("Peru", 14, False),  # NOAA-20 itself cannot order these months
            stratum("Peru", 0, False),  # NOAA-20 orders them: a real failure
            stratum("Peru", 7, False, evaluable=False),
        ],
    }
    noaa20 = {
        "strata": [
            stratum("Peru", 1, True, 0.95),
            stratum("Peru", 14, False, 0.7),
            stratum("Peru", 0, True, 0.9),
        ]
    }
    result = apply_noise_ceiling(modis, noaa20)
    by_biome = {s["biome"]: s for s in result["strata"]}
    assert by_biome[14]["below_noise_ceiling"] and not by_biome[14]["evaluable"] and not by_biome[14]["passed"]
    assert by_biome[0]["evaluable"] and not by_biome[0]["passed"]
    assert not by_biome[7]["evaluable"] and not by_biome[7]["below_noise_ceiling"]
    assert result["strict_passed_fraction"] == 1 / 3
    assert result["passed_fraction"] == 1 / 2
    assert result["below_noise_ceiling"] == 1
    assert result["strict_passed"] is False


def test_leave_country_out_predicts_through_other_countries_only():
    data = pairs("Brazil", 7, 4.0) + pairs("Australia", 7, 4.0) + pairs("Peru", 7, 4.0) + pairs("Peru", 1, 8.0)
    result = validate_countries(data)
    peru = next(r for r in result["countries"] if r["country"] == "Peru")
    # Biome 7 transfers exactly; biome 1 exists nowhere else, so it goes through the world aggregate.
    assert peru["fallback_levels"].get("world_biome") == 72
    assert peru["fallback_levels"].get("global") == 72
    assert peru["relative_bias"] < 0
    brazil = next(r for r in result["countries"] if r["country"] == "Brazil")
    assert brazil["passed"] and abs(brazil["relative_bias"]) < 1e-9
    assert result["kind"] == "reported_not_gated"
