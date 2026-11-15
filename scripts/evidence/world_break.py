"""The 2012 sensor break in every calibration country: raw pixels versus the harmonized record.

For each country, the mean annual total of 2012-2023 (VIIRS era) is divided by the mean of 2003-2011 (MODIS era),
once for raw pixel counts (MODIS before 2012, MODIS and VIIRS after) and once for the harmonized record. Both are
computed over the same cells: the country x biome strata with harmonized values before 2012 (validated strata), so a
stratum that abstains in the MODIS era does not inflate the harmonized ratio.

A ratio near 1 means a stable record; the raw ratio adds the sensor change to any real change in fire activity.

Usage (repository root, server environment):
    .venv/Scripts/python.exe scripts/evidence/world_break.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from peru_case import product_folder  # noqa: E402


def main() -> None:
    folder, manifest = product_folder()
    path = (folder / "harmonized_cell_day.parquet").as_posix()
    countries = sorted({s["country"] for s in (manifest.get("validation") or {}).get("terra_aqua", {}).get("strata", [])})
    con = duckdb.connect()
    rows = con.execute(
        f"""WITH h AS (SELECT * FROM read_parquet('{path}') WHERE country IN (SELECT unnest(?::VARCHAR[]))),
            strata AS (SELECT DISTINCT country, biome FROM h
                       WHERE year(day) BETWEEN 2003 AND 2011 AND active_harmonized IS NOT NULL)
        SELECT h.country, year(h.day) y, sum(h.pixel_rows), sum(h.active_harmonized)
        FROM h JOIN strata USING (country, biome)
        WHERE year(h.day) BETWEEN 2003 AND 2023 GROUP BY ALL ORDER BY 1, 2""",
        [countries],
    ).fetchall()
    by_country: dict[str, dict[int, tuple[float, float]]] = {}
    for country, year, raw, harmonized in rows:
        by_country.setdefault(country, {})[int(year)] = (float(raw or 0), float(harmonized or 0))
    results = []
    for country, years in sorted(by_country.items()):
        modis = [years[y] for y in range(2003, 2012) if y in years]
        viirs = [years[y] for y in range(2012, 2024) if y in years]
        if len(modis) < 5 or len(viirs) < 5:
            continue
        raw_ratio = statistics.mean(v[0] for v in viirs) / max(statistics.mean(v[0] for v in modis), 1e-9)
        harmonized_ratio = statistics.mean(v[1] for v in viirs) / max(statistics.mean(v[1] for v in modis), 1e-9)
        results.append({"country": country, "raw_pixels_ratio": round(raw_ratio, 2),
                        "harmonized_ratio": round(harmonized_ratio, 2), "years_modis": len(modis),
                        "years_viirs": len(viirs)})
    summary = {
        "countries": len(results),
        "median_raw_pixels_ratio": round(statistics.median(r["raw_pixels_ratio"] for r in results), 2),
        "median_harmonized_ratio": round(statistics.median(r["harmonized_ratio"] for r in results), 2),
        "countries_where_harmonized_is_closer_to_1": sum(
            abs(r["harmonized_ratio"] - 1) < abs(r["raw_pixels_ratio"] - 1) for r in results),
    }
    out = {"dataset_id": manifest["id"], "method_version": manifest.get("method_version"),
           "definition": __doc__.split("\n\n")[1].replace("\n", " "), "summary": summary, "by_country": results}
    target = ROOT / "data/reports" / f"world_break_{manifest['id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("written:", target)


if __name__ == "__main__":
    main()
