"""Tree-cover loss by dominant driver for every country and first-level unit (Global Forest Watch, UMD/Hansen).

Source: Global Forest Watch country statistics workbook ``global.xlsx`` (version 2025, tree-cover loss 2001-2025,
canopy >= 30 %), CC BY 4.0. Sheets "Country drivers" and "Subnational 1 drivers" give hectares of loss per year by
dominant driver, one of which is "Wildfire" (Sims et al. 2025, dominant driver per 1 km cell). It extends NINA's
forest context beyond Peru, where the report keeps the cell-level Hansen layer.

Usage (from packages/nina):
    uv run python -m nina.io.forest_drivers --workspace ../.. --download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import truststore

from nina.io.xlsx import read_sheet

URL = "https://gfw2-data.s3.amazonaws.com/country-pages/country_stats/download/2025/global.xlsx"
LICENSE = "CC BY 4.0 (Global Forest Watch; Hansen/UMD/Google/USGS/NASA; drivers: Sims et al. 2025)"
THRESHOLD = 30
SHEETS = {"country": (4, "Country drivers"), "subnational1": (9, "Subnational 1 drivers")}


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


def sheet_rows(path: Path, number: int, expected: list[str]) -> list[dict]:
    rows = read_sheet(path, number)
    header = [str(v).strip() if v is not None else "" for v in rows[0]]
    if header[: len(expected)] != expected:
        raise ValueError(f"sheet {number} header {header} is not {expected}")
    return [dict(zip(header, row, strict=False)) for row in rows[1:] if row]


def build(workspace: Path, *, fetch: bool) -> dict:
    raw = workspace / "source/downloads/forest/gfw_global_2025.xlsx"
    if fetch:
        download(raw)
    if not raw.exists():
        raise SystemExit(f"Missing {raw}; run with --download")
    frames, counts = [], {}
    for level, (number, _name) in SHEETS.items():
        expected = (["country", "threshold", "driver", "year", "tc_loss_ha"] if level == "country"
                    else ["country", "subnational1", "threshold", "driver", "year", "tc_loss_ha"])
        rows = sheet_rows(raw, number, expected)
        frame = pd.DataFrame(rows)
        read = len(frame)
        frame = frame[pd.to_numeric(frame["threshold"], errors="coerce") == THRESHOLD]
        frame = frame.assign(level=level, unit=frame["country"] if level == "country" else frame["subnational1"],
                             year=pd.to_numeric(frame["year"], errors="coerce"),
                             tc_loss_ha=pd.to_numeric(frame["tc_loss_ha"], errors="coerce"))
        bad = frame["year"].isna() | frame["tc_loss_ha"].isna()
        counts[level] = {"rows_read": read, "rows_threshold_30": len(frame), "rows_rejected": int(bad.sum())}
        frames.append(frame.loc[~bad, ["level", "country", "unit", "driver", "year", "tc_loss_ha"]])
    table = pd.concat(frames, ignore_index=True)
    table["year"] = table["year"].astype(int)
    folder = workspace / "source/context/forest_drivers"
    folder.mkdir(parents=True, exist_ok=True)
    table.to_parquet(folder / "gfw_drivers.parquet", index=False)
    manifest = {
        "name": "gfw_drivers",
        "product": "Tree-cover loss by dominant driver, canopy >= 30 %, Global Forest Watch statistics v2025",
        "url": URL,
        "license": LICENSE,
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "retrieved": datetime.fromtimestamp(raw.stat().st_mtime, UTC).date().isoformat(),
        "counts": counts,
        "years": [int(table["year"].min()), int(table["year"].max())],
        "countries": int(table.loc[table["level"] == "country", "country"].nunique()),
        "drivers": sorted(table["driver"].unique().tolist()),
        "note": "Dominant driver per 1 km cell (Sims et al. 2025): 'Wildfire' marks cells where fire dominated the "
                "loss, not every hectare lost to fire.",
    }
    (folder / "gfw_drivers.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.workspace.resolve(), fetch=args.download), indent=1))


if __name__ == "__main__":
    main()
