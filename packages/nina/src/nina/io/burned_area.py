"""Monthly burned area by country and first-level unit: MODIS MCD64A1 (collection 6.1) aggregated by GWIS.

Source: Global Wildfire Information System (JRC / Copernicus EMS), country profile download
"MCD64A1_burned_area_full_dataset_2002_2025" (CC BY 4.0). One row per month and GADM level-1 unit with hectares
burned by land cover class (forest, savannas, shrublands/grasslands, croplands, other).

This is an independent, validated burned-area product (500 m), not derived from the hotspots NINA harmonizes, so it
complements them: hotspots say where and when fire was active; MCD64A1 estimates the area that burned. Small fires
(well under 25 ha, one 500 m pixel) are often missed.

Usage (from packages/nina):
    uv run python -m nina.io.burned_area --workspace ../.. --download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import truststore

URL = ("https://data.effis.emergency.copernicus.eu/apps/country.profile/"
       "MCD64A1_burned_area_full_dataset_2002_2025.zip")
LICENSE = "CC BY 4.0 (GWIS, European Commission Joint Research Centre)"
CLASSES = ["forest", "savannas", "shrublands_grasslands", "croplands", "other"]


def download(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    client = httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=300, follow_redirects=True,
                          headers={"User-Agent": "nina-pipeline"})
    with client, client.stream("GET", URL) as response:
        response.raise_for_status()
        part = target.with_suffix(".part")
        with part.open("wb") as stream:
            for block in response.iter_bytes():
                stream.write(block)
    part.replace(target)
    return target


def build(workspace: Path, *, fetch: bool) -> dict:
    raw = workspace / "source/downloads/burned_area/MCD64A1_burned_area_full_dataset_2002_2025.zip"
    if fetch:
        download(raw)
    if not raw.exists():
        raise SystemExit(f"Missing {raw}; run with --download")
    folder = workspace / "source/context/burned_area"
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(raw) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".csv"))
        csv_path = folder / "gwis_mcd64a1.csv"
        csv_path.write_bytes(archive.read(member))
    connection = duckdb.connect()
    total = " + ".join(f"coalesce({c},0)" for c in CLASSES)
    connection.execute(f"""CREATE TABLE burned AS SELECT year::INTEGER AS year, month::INTEGER AS month,
        gid_0 AS iso3, country, gid_1, region, {", ".join(f"{c}::DOUBLE AS {c}" for c in CLASSES)},
        ({total})::DOUBLE AS burned_ha
        FROM read_csv('{csv_path.as_posix()}', header=true)""")
    rows, rejected = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE year IS NULL OR month NOT BETWEEN 1 AND 12 OR iso3 IS NULL) "
        "FROM burned").fetchall()[0]
    connection.execute("DELETE FROM burned WHERE year IS NULL OR month NOT BETWEEN 1 AND 12 OR iso3 IS NULL")
    target = folder / "gwis_mcd64a1_admin1.parquet"
    connection.execute(f"COPY (SELECT * FROM burned ORDER BY iso3, gid_1, year, month) TO '{target.as_posix()}' "
                       "(FORMAT PARQUET, COMPRESSION ZSTD)")
    first, last, countries, units = connection.execute(
        "SELECT min(year*100+month), max(year*100+month), count(DISTINCT iso3), count(DISTINCT gid_1) FROM burned"
    ).fetchall()[0]
    csv_path.unlink()
    manifest = {
        "name": "gwis_mcd64a1_admin1",
        "product": "MODIS MCD64A1 collection 6.1 burned area, monthly, aggregated by GWIS to GADM level 1",
        "url": URL,
        "license": LICENSE,
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "retrieved": datetime.fromtimestamp(raw.stat().st_mtime, UTC).date().isoformat(),
        "rows_read": int(rows),
        "rows_rejected": int(rejected),
        "first_month": f"{first // 100}-{first % 100:02d}",
        "last_month": f"{last // 100}-{last % 100:02d}",
        "countries": int(countries),
        "units": int(units),
        "classes": CLASSES,
        "note": "500 m product: fires much smaller than one pixel (about 25 ha) are often missed. Independent of "
                "the active-fire hotspots harmonized by NINA.",
    }
    (folder / "gwis_mcd64a1_admin1.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.workspace.resolve(), fetch=args.download), indent=1))


if __name__ == "__main__":
    main()
