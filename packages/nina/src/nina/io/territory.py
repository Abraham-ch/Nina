"""Territorial context layers for the evidence report (docs/TERRITORIAL_REPORT.md).

Builds, from local inputs only:

- Peruvian districts with their UBIGEO code and the H3 cells whose centre falls inside each one;
- INDECI/SINPAD forest-fire emergencies with a single schema across releases;
- fire events: harmonized cell-days grouped by spatial adjacency and a short temporal gap.

Outputs go to ``source/context/`` (not versioned). Run from ``packages/nina/``::

    uv run python -m nina.io.territory --workspace ../..
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import h3
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import mapping, shape

from nina.io.harmonization import file_digest, log, sql_literal, write_json

H3_RESOLUTION = 7
EVENT_GAP_DAYS = 2  # same practice as FET (48 h without updates) and ST-DBSCAN studies
DISTRICTS_URL = "https://github.com/juaneladio/peru-geojson"
INDECI_URL = (
    "https://www.datosabiertos.gob.pe/dataset/emergencias-y-da%C3%B1os-nivel-nacional-por-departamento"
)
FOREST_FIRE_LABELS = ("INCENDIO FORESTAL", "INCENDIOS FORESTALES")
MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
    "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
VIIRS_PLATFORMS = ("S-NPP", "NOAA-20", "NOAA-21")


def ascii_key(text: str | None) -> str:
    """Uppercase ASCII key used to join names written with and without accents."""
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(plain.upper().split())


@dataclass(frozen=True)
class District:
    ubigeo: str
    department: str
    province: str
    district: str
    geometry: Any


def load_districts(path: Path) -> list[District]:
    """Districts of the INEI/MINAM layer with valid geometries and 6-digit UBIGEO codes."""
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    districts = []
    for feature in features:
        props = feature["properties"]
        if not feature.get("geometry"):
            log("district_without_geometry", ubigeo=str(props.get("IDDIST")), name=props.get("NOMBDIST"))
            continue
        geometry = shapely.make_valid(shape(feature["geometry"]))
        districts.append(
            District(
                ubigeo=str(props["IDDIST"]).zfill(6),
                department=str(props["NOMBDEP"]).strip(),
                province=str(props["NOMBPROV"]).strip(),
                district=str(props["NOMBDIST"]).strip(),
                geometry=geometry,
            )
        )
    return districts


def district_cells(districts: list[District], resolution: int = H3_RESOLUTION) -> pd.DataFrame:
    """H3 cells whose centre lies inside each district.

    A district smaller than one cell gets the cell that contains its representative point, unless
    that cell already belongs to another district, so every cell has exactly one district.
    """
    owner: dict[str, str] = {}
    for item in districts:
        parts = (
            list(item.geometry.geoms) if hasattr(item.geometry, "geoms") else [item.geometry]
        )
        for part in parts:
            if part.geom_type != "Polygon" or part.is_empty:
                continue
            for cell in h3.geo_to_cells(mapping(part), resolution):
                owner.setdefault(str(cell), item.ubigeo)
    assigned = set(owner.values())
    for item in districts:
        if item.ubigeo in assigned:
            continue
        point = item.geometry.representative_point()
        owner.setdefault(str(h3.latlng_to_cell(point.y, point.x, resolution)), item.ubigeo)
    return pd.DataFrame({"cell": list(owner), "ubigeo": list(owner.values())})


def districts_geojson(districts: list[District], tolerance: float = 0.001) -> dict[str, Any]:
    """Simplified GeoJSON with the report's property names."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ubigeo": item.ubigeo,
                    "department_code": item.ubigeo[:2],
                    "province_code": item.ubigeo[:4],
                    "department": item.department,
                    "province": item.province,
                    "district": item.district,
                },
                "geometry": mapping(item.geometry.simplify(tolerance, preserve_topology=True)),
            }
            for item in districts
        ],
    }


def indeci_forest_fires(connection: duckdb.DuckDBPyConnection, paths: list[Path]) -> pd.DataFrame:
    """Forest-fire emergencies from the INDECI releases, with one schema.

    The 2003–2025 file uses ``dd/mm/yyyy`` and ``INCENDIO FORESTAL``; the 2026 release uses
    ``mm/dd/yy``, ``INCENDIOS FORESTALES`` and renamed columns. Both are mapped here.
    """
    frames = []
    for path in paths:
        connection.execute(
            f"""CREATE OR REPLACE TEMP TABLE raw_indeci AS SELECT * FROM read_csv({sql_literal(path)},
            delim=';', header=true, encoding='latin-1', all_varchar=true, ignore_errors=true)"""
        )
        columns = {ascii_key(row[0]): row[0] for row in connection.execute("DESCRIBE raw_indeci").fetchall()}

        def column(*candidates: str, _columns: dict[str, str] = columns) -> str:
            for candidate in candidates:
                if candidate in _columns:
                    return '"' + _columns[candidate] + '"'
            raise KeyError(candidates)

        code = column("CODIGO DE EMERGENCIA-SINPAD", "CODIGO EMERGENCIA INPAD")
        when = column("FECHA DE LA EMER", "FECHA DE EMERGENCIA")
        ubigeo = column("COD. DISTRITO", "COD_UBIGEO")
        stated_year = f"try_cast({column('ANO')} AS INTEGER)"
        stated_month = "NULL::INTEGER"
        if "MES" in columns:
            month_text = f"upper(trim({column('MES')}))"
            stated_month = (
                f"coalesce(try_cast({month_text} AS INTEGER), CASE {month_text} "
                + " ".join(f"WHEN '{name}' THEN {number}" for name, number in MONTHS.items())
                + " END)"
            )
        # Releases mix day-first and month-first dates with 2- or 4-digit years. A candidate is
        # accepted only when it matches the row's own year and month columns; otherwise the first
        # day of the stated month is used and the row is flagged, never dropped.
        formats = ["%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%m/%d/%y"]
        if "CODIGO DE EMERGENCIA-SINPAD" not in columns:
            formats = ["%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y"]
        candidates = ",".join(
            f"CASE WHEN year(try_strptime({when}, '{fmt}')) = {stated_year} "
            f"AND ({stated_month} IS NULL OR month(try_strptime({when}, '{fmt}')) = {stated_month}) "
            f"THEN try_strptime({when}, '{fmt}') END"
            for fmt in formats
        )
        fallback = f"make_date({stated_year}, {stated_month}, 1)"
        labels = ",".join(sql_literal(label) for label in FOREST_FIRE_LABELS)
        frame = connection.execute(
            f"""SELECT {code} AS code,
                coalesce({candidates}, {fallback})::DATE AS day,
                coalesce({candidates}) IS NULL AS date_imputed,
                lpad(trim({ubigeo}), 6, '0') AS ubigeo,
                trim({column("DPTO.", "DEP")}) AS department,
                trim({column("PROV.", "PROV")}) AS province,
                trim({column("DIST.", "DIST")}) AS district,
                try_cast({column("FALLECIDOS")} AS INTEGER) AS deaths,
                try_cast({column("DESAPARECIDOS")} AS INTEGER) AS missing,
                try_cast({column("LESIONADOS")} AS INTEGER) AS injured,
                try_cast({column("DAMNIFICADOS")} AS INTEGER) AS homeless,
                try_cast({column("AFECTADOS")} AS INTEGER) AS affected,
                {sql_literal(path.name)} AS source_file
            FROM raw_indeci WHERE upper(trim({column("PELIGRO")})) IN ({labels})"""
        ).df()
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    rejected = int(result["day"].isna().sum())
    if rejected:
        log("indeci_rows_without_date", rows=rejected)
    result = result.dropna(subset=["day"]).drop_duplicates(subset=["code"])
    result.attrs["rows_without_date"] = rejected
    result["year"] = pd.to_datetime(result["day"]).dt.year
    result["month"] = pd.to_datetime(result["day"]).dt.month
    return result.sort_values(["day", "code"]).reset_index(drop=True)


class UnionFind:
    """Disjoint sets over integer nodes, with path halving and union by size."""

    def __init__(self, size: int) -> None:
        self.parent = np.arange(size, dtype=np.int64)
        self.size = np.ones(size, dtype=np.int64)

    def find(self, node: int) -> int:
        parent = self.parent
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = int(parent[node])
        return node

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return
        if self.size[root_a] < self.size[root_b]:
            root_a, root_b = root_b, root_a
        self.parent[root_b] = root_a
        self.size[root_a] += self.size[root_b]


def fire_events(cell_days: pd.DataFrame, gap_days: int = EVENT_GAP_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Group cell-days into fire events.

    Two cell-days belong to the same event when their cells are the same or neighbours (H3 ring 1)
    and their dates differ by at most ``gap_days``. Input columns: ``cell``, ``day``,
    ``active_harmonized`` and ``source_mix``. Returns the events and the cell-day membership.
    """
    frame = cell_days.sort_values(["cell", "day"]).reset_index(drop=True)
    if frame.empty:
        empty = pd.DataFrame(columns=["event_id", "cell", "day"])
        return pd.DataFrame(), empty
    ordinal = pd.to_datetime(frame["day"]).map(pd.Timestamp.toordinal).to_numpy(dtype=np.int64)
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    cells = frame["cell"].to_numpy()
    boundaries = np.flatnonzero(np.r_[True, cells[1:] != cells[:-1], True])
    for begin, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        starts[str(cells[begin])], ends[str(cells[begin])] = int(begin), int(end)
    forest = UnionFind(len(frame))
    for cell, begin in starts.items():
        end = ends[cell]
        days = ordinal[begin:end]
        for offset in np.flatnonzero(np.diff(days) <= gap_days):
            forest.union(begin + int(offset), begin + int(offset) + 1)
        for neighbour in h3.grid_ring(cell, 1):
            if neighbour not in starts or neighbour <= cell:
                continue
            other_begin, other_end = starts[neighbour], ends[neighbour]
            other = ordinal[other_begin:other_end]
            low = np.searchsorted(other, days - gap_days, side="left")
            high = np.searchsorted(other, days + gap_days, side="right")
            for index in np.flatnonzero(high > low):
                for match in range(int(low[index]), int(high[index])):
                    forest.union(begin + int(index), other_begin + match)
    roots = np.fromiter((forest.find(i) for i in range(len(frame))), dtype=np.int64, count=len(frame))
    _, event_index = np.unique(roots, return_inverse=True)
    frame["event_id"] = event_index.astype(np.int64)
    centres = {cell: h3.cell_to_latlng(cell) for cell in starts}
    frame["latitude"] = frame["cell"].map(lambda c: centres[c][0])
    frame["longitude"] = frame["cell"].map(lambda c: centres[c][1])
    frame["viirs"] = frame["source_mix"].fillna("").map(
        lambda mix: any(platform in mix for platform in VIIRS_PLATFORMS)
    )
    grouped = frame.groupby("event_id")
    events = pd.DataFrame(
        {
            "start_day": grouped["day"].min(),
            "end_day": grouped["day"].max(),
            "cell_days": grouped.size(),
            "cells": grouped["cell"].nunique(),
            "max_daily_cells": frame.groupby(["event_id", "day"]).size().groupby("event_id").max(),
            "activity_equiv": grouped["active_harmonized"].sum(min_count=1),
            "latitude": grouped["latitude"].mean(),
            "longitude": grouped["longitude"].mean(),
            "viirs_share": grouped["viirs"].mean(),
        }
    ).reset_index()
    events["duration_days"] = (
        pd.to_datetime(events["end_day"]) - pd.to_datetime(events["start_day"])
    ).dt.days + 1
    events["era"] = np.where(events["viirs_share"] >= 0.5, "viirs", "modis")
    return events, frame[["event_id", "cell", "day"]]


def majority_district(membership: pd.DataFrame, cell_district: pd.DataFrame) -> pd.Series:
    """District holding most cell-days of each event (empty when no cell is in Peru)."""
    joined = membership.merge(cell_district, on="cell", how="left").dropna(subset=["ubigeo"])
    if joined.empty:
        return pd.Series(dtype=object)
    counts = joined.groupby(["event_id", "ubigeo"]).size().reset_index(name="n")
    top = counts.sort_values(["event_id", "n", "ubigeo"], ascending=[True, False, True])
    return top.drop_duplicates("event_id").set_index("event_id")["ubigeo"]


def product_folder(workspace: Path) -> tuple[Path, dict[str, Any]]:
    for root in [workspace / "source/harmonized", workspace / "source/review"]:
        pointer = root / "current.json"
        if pointer.exists():
            manifest = json.loads(pointer.read_text(encoding="utf-8"))
            return root / manifest["id"], manifest
    raise SystemExit("No harmonized product in source/harmonized or source/review")


def build(workspace: Path, countries: list[str]) -> dict[str, Any]:
    """Build the three layers and write them with a manifest."""
    context = workspace / "source/context"
    boundaries = workspace / "source/downloads/boundaries/peru_distrital_simple.geojson"
    indeci_files = [
        workspace / "source/downloads/national/indeci/BD_2003-2025_EMERGENCIAS.csv",
        workspace / "source/downloads/national/indeci/BD_2026_Semestre_I.csv",
    ]
    folder, product = product_folder(workspace)
    connection = duckdb.connect()

    districts = load_districts(boundaries)
    mapping_frame = district_cells(districts)
    (context / "districts").mkdir(parents=True, exist_ok=True)
    write_json(context / "districts/peru_districts.geojson", districts_geojson(districts))
    mapping_frame.to_parquet(context / "districts/cell_district.parquet", index=False)
    log("districts", districts=len(districts), cells=len(mapping_frame))

    emergencies = indeci_forest_fires(connection, [p for p in indeci_files if p.exists()])
    (context / "indeci").mkdir(parents=True, exist_ok=True)
    emergencies.to_parquet(context / "indeci/forest_fire_emergencies.parquet", index=False)
    known = set(mapping_frame["ubigeo"])
    unmatched = int((~emergencies["ubigeo"].isin(known)).sum())
    log("indeci", emergencies=len(emergencies), unmatched_ubigeo=unmatched)

    event_frames, member_frames, stats = [], [], {}
    offset = 0
    for country in countries:
        cell_days = connection.execute(
            f"""SELECT cell, day, active_harmonized, source_mix
            FROM read_parquet({sql_literal(folder / "harmonized_cell_day.parquet")})
            WHERE country = ?""",
            [country],
        ).df()
        events, membership = fire_events(cell_days)
        if events.empty:
            continue
        events["event_id"] += offset
        membership["event_id"] += offset
        offset = int(events["event_id"].max()) + 1
        events.insert(1, "country", country)
        events["ubigeo"] = events["event_id"].map(majority_district(membership, mapping_frame))
        event_frames.append(events)
        member_frames.append(membership)
        stats[country] = {"cell_days": len(cell_days), "events": len(events)}
        log("events", country=country, cell_days=len(cell_days), events=len(events))
    (context / "events").mkdir(parents=True, exist_ok=True)
    all_events = pd.concat(event_frames, ignore_index=True)
    all_events.to_parquet(context / "events/fire_events.parquet", index=False)
    pd.concat(member_frames, ignore_index=True).to_parquet(
        context / "events/event_cell_days.parquet", index=False
    )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_id": product["id"],
        "method_version": product["method_version"],
        "h3_resolution": H3_RESOLUTION,
        "districts": {
            "source": DISTRICTS_URL,
            "license": "MPL-2.0 (derived from INEI/MINAM district limits)",
            "file_sha256": file_digest(boundaries),
            "districts": len(districts),
            "cells": len(mapping_frame),
            "rule": "cell centre inside the district polygon; districts smaller than a cell get the "
            "cell of their representative point when it is free",
        },
        "indeci": {
            "source": INDECI_URL,
            "license": "ODC-BY",
            "files": {p.name: file_digest(p) for p in indeci_files if p.exists()},
            "hazards": list(FOREST_FIRE_LABELS),
            "emergencies": len(emergencies),
            "years": [int(emergencies["year"].min()), int(emergencies["year"].max())],
            "unmatched_ubigeo": unmatched,
            "date_imputed_to_first_of_month": int(emergencies["date_imputed"].sum()),
            "rows_without_date": int(emergencies.attrs.get("rows_without_date", 0)),
            "note": "Counts registered emergencies with damage assessment, not every fire.",
        },
        "events": {
            "rule": f"same or neighbouring H3 cell (ring 1) and dates at most {EVENT_GAP_DAYS} days apart",
            "input": "harmonized_cell_day (observed cell-days, all sources)",
            "countries": stats,
            "comparability": "Event counts depend on sensor sensitivity: compare years within one era "
            "(VIIRS from 2012-01-20). `era` and `viirs_share` are given per event.",
        },
    }
    write_json(context / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--countries", nargs="+", default=["Peru"])
    args = parser.parse_args()
    manifest = build(args.workspace.resolve(), args.countries)
    print(json.dumps({k: manifest[k] for k in ["districts", "indeci", "events"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
