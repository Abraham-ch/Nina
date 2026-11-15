"""Global evidence for the landing page (web/public/assets/world-evidence.json), from the 0.5.0 run.

Reads the offline pipeline's model and validation reports and the 2012 break summary; writes only aggregate figures.

Usage (repository root, server environment, after scripts/evidence/world_break.py):
    .venv/Scripts/python.exe scripts/evidence/world_evidence.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
    target = ROOT / "web/public/assets/world-evidence.json"
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
