"""Parámetros de la armonización (AGENTS.md §9.3), sobreescribibles por variables de entorno."""

import os
from datetime import date


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


HARMONIZATION_VERSION = _env("HARMONIZATION_VERSION", "0.5.0")
MIN_CONFIDENCE_CLASS = _env("MIN_CONFIDENCE_CLASS", "nominal")
KEEP_TYPES = [int(t) for t in _env("KEEP_TYPES", "0").split(",")]
H3_RES = int(_env("H3_RES", "7"))
PROVISIONAL_DAYS = int(_env("PROVISIONAL_DAYS", "150"))
FIRMS_MAX_DAY_RANGE = int(_env("FIRMS_MAX_DAY_RANGE", "5"))
STATIC_SOURCE_MIN_DAYS_PER_YEAR = int(_env("STATIC_SOURCE_MIN_DAYS_PER_YEAR", "16"))
STATIC_SOURCE_H3_RES = int(_env("STATIC_SOURCE_H3_RES", "8"))
VOLCANO_BUFFER_KM = float(_env("VOLCANO_BUFFER_KM", "2"))
SERIES_START_DATE = date.fromisoformat(_env("SERIES_START_DATE", "2000-11-01"))
MIN_AGG_DAYS_FOR_ANOMALY = int(_env("MIN_AGG_DAYS_FOR_ANOMALY", "8"))

# Calibration countries with their full FIRMS history, as Natural Earth names (ADR 0006). The first five are
# the 0.4.0 set. FIRMS file names of the same countries are in nina.io.acquire.
CORE_CALIBRATION_COUNTRIES = frozenset(
    {"Brazil", "Australia", "Indonesia", "United States of America", "Peru"}
)
CALIBRATION_COUNTRIES = CORE_CALIBRATION_COUNTRIES | frozenset(
    {
        "Dem. Rep. Congo", "Russia", "India", "Canada", "Mexico",
        "Bolivia", "Colombia", "Ecuador", "Chile", "Argentina", "Paraguay", "Venezuela", "Honduras",
        "Zambia", "Nigeria", "Ethiopia", "Madagascar", "South Africa",
        "China", "Myanmar", "Kazakhstan", "Mongolia",
        "Portugal", "Spain", "Greece", "Turkey",
    }
)
