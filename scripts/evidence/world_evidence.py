"""Global evidence for the landing page (web/public/assets/world-evidence.json), from the 0.5.0 run.

Reads the offline pipeline's model and validation reports and the 2012 break summary; writes only aggregate figures.
The "this year" figures (record months of the current year, Peru's September, the Chilecito case) are computed with
the server's harmonized module on the product in source/review (NINA_EXPERIMENTAL_HARMONIZATION=true); results are
stored per selection in data/jobs/harmonized, so a second run is fast.

Usage (repository root, server environment, after scripts/evidence/world_break.py):
    .venv/Scripts/python.exe scripts/evidence/world_evidence.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHILECITO = [[-67.75, -29.35], [-67.05, -29.35], [-67.05, -28.75], [-67.75, -28.75], [-67.75, -29.35]]  # BURN_CASE doc
MIN_YEARS = 15  # a record needs at least 15 earlier years of the same month
MIN_ACTIVITY = 50  # and enough activity not to be noise (VIIRS-equivalent active cell-days)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def this_year(countries: list[str]) -> dict:
    """Record months of the product's last year per country, Peru's September and the Chilecito July."""
    os.environ.setdefault("NINA_EXPERIMENTAL_HARMONIZATION", "true")
    sys.path.insert(0, str(ROOT))
    from nina.harmonized import HarmonizedSelection, create_analysis, published

    manifest, _ = published()
    year = int(manifest["as_of_date"][:4])
    last_month = int(manifest["as_of_date"][5:7]) - 1  # last complete month

    def analysis(country, month, geometry=None):
        return create_analysis(HarmonizedSelection(country=country, year_start=2002, year_end=year, selected_year=year,
                                                   selected_month=month, geometry=geometry))

    records = []
    for country in countries:
        months = analysis(country, last_month)["months"]
        for month in range(1, last_month + 1):
            now = next((m for m in months if m["year"] == year and m["month"] == month), None)
            if not now or now["value"] is None or now.get("data_gap"):
                continue
            history = [m["value"] for m in months if m["month"] == month and 2003 <= m["year"] < year
                       and m["value"] is not None and not m.get("data_gap")]
            if len(history) < MIN_YEARS or now["value"] < MIN_ACTIVITY or now["value"] <= max(history):
                continue
            median = statistics.median(history)
            records.append({"country": country, "month": month, "value": now["value"], "median": median,
                            "times_median": now["value"] / median if median else None, "years": len(history) + 1,
                            "provisional": bool(now.get("is_provisional"))})
    best = {}
    for r in sorted(records, key=lambda r: -(r["times_median"] or 0)):
        best.setdefault(r["country"], r)
    peru = analysis("Peru", 9)["selected"]
    chile = analysis("world", 7, {"type": "Polygon", "coordinates": [CHILECITO]})["selected"]
    return {
        "year": year,
        "through_month": last_month,
        "record_rule": f"more activity than any same month since 2003, >= {MIN_YEARS} earlier years, >= {MIN_ACTIVITY}",
        "countries_with_record_month": len(best),
        "records_by_country": sorted(best.values(), key=lambda r: -(r["times_median"] or 0)),
        "peru_september": {"value": peru["value"], "median": peru["historical_median"],
                           "anomaly_percent": peru["anomaly_percent"], "rank": peru["rank"], "rank_of": peru["rank_of"],
                           "provisional": peru["is_provisional"]},
        "chilecito_july": {"value": chile["value"], "median": chile["historical_median"], "rank": chile["rank"],
                           "rank_of": chile["rank_of"], "provisional": chile["is_provisional"]},
    }


def main() -> None:
    model = load(ROOT / "source/interim/harmonization/model.json")
    previous = ROOT / "source/interim/harmonization/archive_0.4.0/model.json"
    breaks = load(ROOT / "data/reports" / f"world_break_{load(ROOT / 'source/review/current.json')['id']}.json")
    validation = ROOT / "source/context/validation"
    modis = model["validation"]["terra_aqua"]
    strata = [s for s in modis["strata"] if s["evaluable"]]
    registries = {}
    for name, label in (("events_canada_cnfdb", "Canada"), ("events_usa_nifc", "United States")):
        headline = load(validation / f"{name}.json")["headline"]
        registries[label] = {"rate": headline["rate"], "chance_rate": headline["chance_rate"],
                             "records": headline["records"], "note": headline.get("note")}
    out = {
        "dataset_id": load(ROOT / "source/review/current.json")["id"],
        "method_version": model["method_version"],
        "countries": len(model["configuration"]["calibration_countries"]),
        "archive_share": 0.61,  # bytes of the 2000-2025 FIRMS country archive held by the 31 countries (ADR 0006)
        "modis_gate": {"passed": sum(bool(s["passed"]) for s in strata), "evaluable": len(strata),
                       "fraction": modis["passed_fraction"], "strict_fraction": modis.get("strict_passed_fraction"),
                       "required": modis["minimum_fraction"],
                       "typical_year_error": modis["per_year_error_in_passed_strata"]["yearly_abs_bias_median"]},
        "noaa20_r2": model["validation"]["noaa20"]["overall"]["r2"],
        "outside_calibration_bias": {"now": model["geographic_diagnostic"]["terra_aqua"]["metrics"]["relative_bias"],
                                     "with_five_countries": load(previous)["geographic_diagnostic"]["terra_aqua"]
                                     ["metrics"]["relative_bias"] if previous.exists() else None},
        "break_2012": breaks["summary"],
        "registries": registries,
        "transfer_median_abs_bias": statistics.median(
            abs(c["relative_bias"]) for c in model["country_transfer"]["terra_aqua"]["countries"]
            if c["relative_bias"] is not None),
    }
    out["this_year"] = this_year(model["configuration"]["calibration_countries"])
    target = ROOT / "web/public/assets/world-evidence.json"
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
